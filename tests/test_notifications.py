from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import config
from app.importers.common import FundingCallData
from app.models import FundingCall, NotificationHistory, NotificationRun
from app.services import notifications
from app.services.imports import run_imports
from app.services.notifications import (
    NotificationDeliveryUncertain,
    NotificationEmail,
    NotificationRunFailed,
    NotificationSendError,
    NotificationRunInProgress,
    mark_interrupted_notification,
    run_notification,
    resolve_uncertain_notification,
)
from app.services.search_profiles import save_keyword_settings


class RecordingSender:
    def __init__(self):
        self.messages: list[NotificationEmail] = []

    def send(self, message: NotificationEmail) -> None:
        self.messages.append(message)


def _set_import_data(monkeypatch, *, eura_calls=None, hae_calls=None):
    monkeypatch.setattr("app.services.imports.fetch_eura_calls", lambda client, criteria: eura_calls or [])
    monkeypatch.setattr(
        "app.services.imports.fetch_haeavustuksia_calls",
        lambda client, criteria: hae_calls or [],
    )


def _call(source, source_id, title, *, description="Kuvausteksti", fund="ESR+"):
    return FundingCallData(
        source=source,
        source_id=source_id,
        title=title,
        description=description,
        fund=fund,
        source_url=f"https://example.test/{source_id}",
        raw_data={"id": source_id},
    )


def _next_run():
    return datetime(2027, 1, 1, 9, 0, tzinfo=timezone.utc)


def _run(session, sender, *, key="run-1", retry_failed=False):
    return run_notification(
        session,
        sender,
        run_key=key,
        next_run_at=_next_run(),
        retry_failed=retry_failed,
    )


def test_new_calls_are_durably_queued_with_import_and_resume_after_scoring_failure(
    db_session, monkeypatch,
):
    monkeypatch.setattr(config, "NOTIFICATION_MIN_RELEVANCE_SCORE", 20)
    save_keyword_settings(db_session, ["koulutus"], [])
    eura = _call("EURA", "eura-1", "Koulutus")
    hae = _call("HAEAVUSTUKSIA", "hae-1", "Muu hanke")
    _set_import_data(monkeypatch, eura_calls=[eura], hae_calls=[hae])
    sender = RecordingSender()
    actual_score = notifications.score_funding_calls
    calls_to_import = []
    actual_imports = notifications.run_imports

    def counted_imports(*args, **kwargs):
        calls_to_import.append(kwargs["notification_run_id"])
        return actual_imports(*args, **kwargs)

    def fail_scoring(*args, **kwargs):
        raise RuntimeError("Pisteytys keskeytyi")

    monkeypatch.setattr(notifications, "run_imports", counted_imports)
    monkeypatch.setattr(notifications, "score_funding_calls", fail_scoring)
    with pytest.raises(RuntimeError, match="Pisteytys keskeytyi"):
        _run(db_session, sender)

    run = db_session.scalar(select(NotificationRun).where(NotificationRun.run_key == "run-1"))
    staged = list(db_session.scalars(select(NotificationHistory).where(NotificationHistory.run_id == run.id)))
    assert run.status == "EVALUATING"
    assert len(staged) == 2
    assert {item.status for item in staged} == {"PENDING_EVALUATION"}
    assert db_session.scalar(select(func.count()).select_from(FundingCall)) == 2
    assert sender.messages == []

    monkeypatch.setattr(notifications, "score_funding_calls", actual_score)
    resumed = _run(db_session, sender)
    assert resumed.status == "SENT"
    assert len(resumed.notified_call_ids) == 1
    assert calls_to_import == [run.id]
    assert len(sender.messages) == 1


def test_existing_updates_are_not_queued_again_and_message_contains_required_fields(
    db_session, monkeypatch,
):
    monkeypatch.setattr(config, "NOTIFICATION_MIN_RELEVANCE_SCORE", 20)
    save_keyword_settings(db_session, ["koulutus"], [])
    eura = _call("EURA", "eura-2", "Koulutus")
    hae = _call("HAEAVUSTUKSIA", "hae-2", "Muu hanke")
    _set_import_data(monkeypatch, eura_calls=[eura], hae_calls=[hae])
    sender = RecordingSender()

    result = _run(db_session, sender)
    assert result.status == "SENT"
    assert result.email.subject == "Uusia potentiaalisia hankkeita löytyi"
    assert "Nimi: Koulutus" in result.email.body
    assert "Rahoituslähde: ESR+" in result.email.body
    assert "Kuvaus: Kuvausteksti" in result.email.body
    assert "Lisätiedot: https://example.test/eura-2" in result.email.body
    assert "Lähde: EURA 2021" in result.email.body
    assert db_session.scalar(select(func.count()).select_from(NotificationHistory)) == 2
    assert db_session.scalar(
        select(func.count()).select_from(NotificationHistory).where(NotificationHistory.status == "SENT")
    ) == 1
    repeated = _run(db_session, sender)
    assert repeated.status == "SENT"
    assert repeated.notified_call_ids == result.notified_call_ids
    assert len(sender.messages) == 1

    _set_import_data(
        monkeypatch,
        eura_calls=[_call("EURA", "eura-2", "Päivitetty koulutus")],
        hae_calls=[hae],
    )
    second = _run(db_session, sender, key="run-2")
    assert second.status == "SENT"
    assert second.notified_call_ids == ()
    assert second.email.subject == "Ei uusia potentiaalisia hankkeita"
    assert "molemmille nykyisille lähteille" in second.email.body
    assert "Haeavustuksia.fi ja EURA 2021" in second.email.body
    assert "Seuraava haku: 01.01.2027 klo 09:00 UTC" in second.email.body
    assert db_session.scalar(select(func.count()).select_from(NotificationHistory)) == 2
    assert db_session.scalar(
        select(func.count()).select_from(NotificationHistory).where(NotificationHistory.status == "NOT_SELECTED")
    ) == 1


def test_previously_imported_open_call_is_queued_once_and_expired_call_is_excluded(
    db_session, monkeypatch,
):
    monkeypatch.setattr(config, "NOTIFICATION_MIN_RELEVANCE_SCORE", 20)
    save_keyword_settings(db_session, ["koulutus"], [])
    existing_open_call = _call("EURA", "imported-before-notifications", "Koulutus")
    expired_call = FundingCallData(
        source="HAEAVUSTUKSIA",
        source_id="expired-legacy-call",
        title="Koulutus, haku päättynyt",
        description="Vanha haku",
        fund="ESR+",
        source_url="https://example.test/expired-legacy-call",
        application_end_date=datetime.now(ZoneInfo("Europe/Helsinki")).date() - timedelta(days=1),
        raw_data={"id": "expired-legacy-call"},
    )
    _set_import_data(monkeypatch, eura_calls=[existing_open_call], hae_calls=[expired_call])

    # A normal/manual import creates the project but does not create notification history.
    imported = run_imports(db_session)
    assert imported["eura"]["created"] == 1
    assert db_session.scalar(select(func.count()).select_from(NotificationHistory)) == 0

    sender = RecordingSender()
    result = _run(db_session, sender, key="backfill-existing")
    assert result.status == "SENT"
    assert len(result.notified_call_ids) == 1
    assert "Nimi: Koulutus" in result.email.body
    history = list(db_session.scalars(select(NotificationHistory)))
    assert len(history) == 1
    assert sum(item.status == "SENT" for item in history) == 1
    sent_call = db_session.get(FundingCall, result.notified_call_ids[0])
    assert sent_call.source_id == "imported-before-notifications"
    assert all(
        item.funding_call_id != db_session.scalar(
            select(FundingCall.id).where(FundingCall.source_id == "expired-legacy-call")
        )
        for item in history
    )

    # A later scheduled run sees the same open call but its global history prevents requeueing.
    next_result = _run(db_session, sender, key="backfill-existing-next")
    assert next_result.notified_call_ids == ()
    assert next_result.email.subject == "Ei uusia potentiaalisia hankkeita"
    assert len(list(db_session.scalars(select(NotificationHistory)))) == 1
    assert len(sender.messages) == 2


def test_empty_success_is_saved_and_same_run_is_not_sent_twice(db_session, monkeypatch):
    monkeypatch.setattr(config, "NOTIFICATION_MIN_RELEVANCE_SCORE", 60)
    save_keyword_settings(db_session, ["koulutus"], [])
    _set_import_data(monkeypatch)
    sender = RecordingSender()

    first = _run(db_session, sender, key="empty-1")
    assert first.status == "SENT"
    assert first.notified_call_ids == ()
    assert first.email.subject == "Ei uusia potentiaalisia hankkeita"
    assert "eikä uusia sopiviksi arvioituja hankkeita löytynyt" in first.email.body
    run = db_session.scalar(select(NotificationRun).where(NotificationRun.run_key == "empty-1"))
    assert run.status == "SENT"
    assert run.subject == first.email.subject
    assert run.body == first.email.body
    assert db_session.scalar(select(func.count()).select_from(NotificationHistory)) == 0

    repeated = _run(db_session, sender, key="empty-1")
    assert repeated.status == "SENT"
    assert len(sender.messages) == 1

    next_empty_run = _run(db_session, sender, key="empty-2")
    assert next_empty_run.status == "SENT"
    assert len(sender.messages) == 2
    assert db_session.scalar(select(func.count()).select_from(NotificationRun)) == 2


def test_empty_profile_is_rejected_before_import_and_not_reported_as_empty(db_session, monkeypatch):
    monkeypatch.setattr(config, "NOTIFICATION_MIN_RELEVANCE_SCORE", 20)
    save_keyword_settings(db_session, ["   "], [])
    _set_import_data(monkeypatch, eura_calls=[_call("EURA", "empty-profile", "Koulutus")])
    sender = RecordingSender()

    with pytest.raises(ValueError, match="ei ole kiinnostavia hakusanoja"):
        _run(db_session, sender)

    run = db_session.scalar(select(NotificationRun).where(NotificationRun.run_key == "run-1"))
    assert run.status == "IMPORTING"
    assert "kiinnostavia hakusanoja" in run.last_error
    assert sender.messages == []
    assert db_session.scalar(select(func.count()).select_from(FundingCall)) == 0


def test_partial_import_failure_rolls_back_queue_and_same_run_can_resume(db_session, monkeypatch):
    monkeypatch.setattr(config, "NOTIFICATION_MIN_RELEVANCE_SCORE", 20)
    save_keyword_settings(db_session, ["koulutus"], [])
    eura = _call("EURA", "rollback-eura", "Koulutus")

    def fail_hae(client, criteria):
        raise RuntimeError("Toinen lähde ei vastannut")

    monkeypatch.setattr("app.services.imports.fetch_eura_calls", lambda client, criteria: [eura])
    monkeypatch.setattr("app.services.imports.fetch_haeavustuksia_calls", fail_hae)
    sender = RecordingSender()
    with pytest.raises(RuntimeError, match="Toinen lähde ei vastannut"):
        _run(db_session, sender)

    run = db_session.scalar(select(NotificationRun).where(NotificationRun.run_key == "run-1"))
    assert run.status == "IMPORTING"
    assert db_session.scalar(select(func.count()).select_from(FundingCall)) == 0
    assert db_session.scalar(select(func.count()).select_from(NotificationHistory)) == 0

    _set_import_data(monkeypatch, eura_calls=[eura])
    resumed = _run(db_session, sender)
    assert resumed.status == "SENT"
    assert len(resumed.notified_call_ids) == 1
    assert len(sender.messages) == 1


def test_definite_send_failure_is_recorded_and_requires_explicit_retry(db_session, monkeypatch):
    monkeypatch.setattr(config, "NOTIFICATION_MIN_RELEVANCE_SCORE", 20)
    save_keyword_settings(db_session, ["koulutus"], [])
    _set_import_data(monkeypatch, eura_calls=[_call("EURA", "known-failure", "Koulutus")])

    class FailOnceSender:
        def __init__(self):
            self.attempts = 0

        def send(self, message):
            self.attempts += 1
            if self.attempts == 1:
                raise NotificationSendError("SMTP rejected before acceptance", outcome_unknown=False)

    sender = FailOnceSender()
    with pytest.raises(NotificationSendError):
        _run(db_session, sender)

    run = db_session.scalar(select(NotificationRun).where(NotificationRun.run_key == "run-1"))
    history = db_session.scalar(select(NotificationHistory))
    assert run.status == "FAILED"
    assert history.status == "FAILED"
    with pytest.raises(NotificationRunFailed):
        _run(db_session, sender)
    assert sender.attempts == 1

    result = _run(db_session, sender, retry_failed=True)
    assert result.status == "SENT"
    assert sender.attempts == 2
    assert db_session.scalar(select(NotificationHistory).where(NotificationHistory.status == "SENT")) is not None


def test_uncertain_send_is_recorded_and_never_retried_automatically(db_session, monkeypatch):
    monkeypatch.setattr(config, "NOTIFICATION_MIN_RELEVANCE_SCORE", 20)
    save_keyword_settings(db_session, ["koulutus"], [])
    _set_import_data(monkeypatch, eura_calls=[_call("EURA", "unknown-outcome", "Koulutus")])

    class UncertainSender:
        def __init__(self):
            self.attempts = 0

        def send(self, message):
            self.attempts += 1
            raise NotificationSendError("Connection ended after submit", outcome_unknown=True)

    sender = UncertainSender()
    with pytest.raises(NotificationDeliveryUncertain):
        _run(db_session, sender)

    run = db_session.scalar(select(NotificationRun).where(NotificationRun.run_key == "run-1"))
    history = db_session.scalar(select(NotificationHistory))
    assert run.status == "UNCERTAIN"
    assert history.status == "UNCERTAIN"
    with pytest.raises(NotificationDeliveryUncertain):
        _run(db_session, sender, retry_failed=True)
    assert sender.attempts == 1

    resolved = resolve_uncertain_notification(db_session, "run-1", delivered=True)
    assert resolved.status == "SENT"
    assert len(resolved.notified_call_ids) == 1
    replay = _run(db_session, RecordingSender())
    assert replay.status == "SENT"
    assert sender.attempts == 1


def test_stale_attempting_run_is_marked_uncertain_without_resending(db_session, monkeypatch):
    monkeypatch.setattr(config, "NOTIFICATION_MIN_RELEVANCE_SCORE", 20)
    save_keyword_settings(db_session, ["koulutus"], [])
    _set_import_data(monkeypatch, eura_calls=[_call("EURA", "crash-during-send", "Koulutus")])

    class CrashAfterAttemptStart:
        def send(self, message):
            raise SystemExit("simulated process termination")

    with pytest.raises(SystemExit):
        _run(db_session, CrashAfterAttemptStart())
    run = db_session.scalar(select(NotificationRun).where(NotificationRun.run_key == "run-1"))
    assert run.status == "ATTEMPTING"

    sender = RecordingSender()
    with pytest.raises(NotificationRunInProgress):
        _run(db_session, sender)
    assert db_session.get(NotificationRun, run.id).status == "ATTEMPTING"
    assert sender.messages == []

    recovered = mark_interrupted_notification(
        db_session,
        "run-1",
        expected_attempt_at=run.last_attempt_at,
    )
    assert recovered.status == "UNCERTAIN"
    with pytest.raises(NotificationDeliveryUncertain):
        _run(db_session, sender)
    assert db_session.get(NotificationRun, run.id).status == "UNCERTAIN"
    assert sender.messages == []


def test_concurrent_attempt_cannot_start_second_send(db_session, monkeypatch):
    monkeypatch.setattr(config, "NOTIFICATION_MIN_RELEVANCE_SCORE", 20)
    save_keyword_settings(db_session, ["koulutus"], [])
    _set_import_data(monkeypatch, eura_calls=[_call("EURA", "concurrent", "Koulutus")])
    entered_sender = Event()
    release_sender = Event()

    class BlockingSender:
        def __init__(self):
            self.messages = []

        def send(self, message):
            self.messages.append(message)
            entered_sender.set()
            assert release_sender.wait(timeout=5)

    sender = BlockingSender()
    first_results = []
    first_errors = []

    def first_attempt():
        try:
            with Session(db_session.get_bind()) as session:
                first_results.append(_run(session, sender))
        except Exception as exc:  # surfaced in the test thread below
            first_errors.append(exc)

    worker = Thread(target=first_attempt)
    worker.start()
    assert entered_sender.wait(timeout=5)
    try:
        with Session(db_session.get_bind()) as second_session:
            with pytest.raises(NotificationRunInProgress):
                _run(second_session, sender)
    finally:
        release_sender.set()
        worker.join(timeout=5)

    assert not worker.is_alive()
    assert first_errors == []
    assert len(first_results) == 1
    assert first_results[0].status == "SENT"
    assert len(sender.messages) == 1


def test_missing_relevance_threshold_is_saved_as_configuration_error(db_session, monkeypatch):
    monkeypatch.setattr(config, "NOTIFICATION_MIN_RELEVANCE_SCORE", None)
    sender = RecordingSender()

    with pytest.raises(ValueError, match="Aseta NOTIFICATION_MIN_RELEVANCE_SCORE"):
        _run(db_session, sender)

    run = db_session.scalar(select(NotificationRun).where(NotificationRun.run_key == "run-1"))
    assert run.status == "IMPORTING"
    assert "NOTIFICATION_MIN_RELEVANCE_SCORE" in run.last_error
    assert sender.messages == []
