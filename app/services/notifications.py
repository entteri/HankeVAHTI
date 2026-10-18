"""Durable notification runs with an injected, non-configured delivery boundary."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import config
from app.evaluators.relevance import normalize_keywords
from app.models import Evaluation, FundingCall, NotificationHistory, NotificationRun
from app.services.funding_calls import _source_url
from app.services.imports import run_imports
from app.services.relevance import score_funding_calls
from app.services.search_profiles import get_relevance_profile


@dataclass(frozen=True)
class NotificationEmail:
    recipient: str | None
    subject: str
    body: str


class NotificationSender(Protocol):
    """Transport boundary; this project has no production mail transport yet."""

    def send(self, message: NotificationEmail) -> None: ...


class NotificationSendError(Exception):
    """A sender error whose delivery certainty is explicitly supplied by its adapter."""

    def __init__(self, message: str, *, outcome_unknown: bool) -> None:
        super().__init__(message)
        self.outcome_unknown = outcome_unknown


class NotificationDeliveryUncertain(RuntimeError):
    """The message may have been delivered; automatic retry is intentionally blocked."""


class NotificationRunFailed(RuntimeError):
    """A definite send failure requires an explicit retry of the same run."""


class NotificationRunInProgress(RuntimeError):
    """Another worker has already claimed this run for delivery."""


@dataclass(frozen=True)
class NotificationRunResult:
    run_key: str
    status: str
    notified_call_ids: tuple[int, ...]
    email: NotificationEmail | None


def _minimum_score() -> int:
    score = config.NOTIFICATION_MIN_RELEVANCE_SCORE
    if score is None:
        raise ValueError("Aseta NOTIFICATION_MIN_RELEVANCE_SCORE ennen ilmoitusajoa.")
    if not 0 <= score <= 100:
        raise ValueError("NOTIFICATION_MIN_RELEVANCE_SCORE-arvon pitää olla välillä 0–100.")
    return score


def _validate_profile(session: Session) -> None:
    profile = get_relevance_profile(session)
    if profile is None or not profile.active:
        raise ValueError("Tallenna aktiivinen relevanssin hakuprofiili ennen ilmoitusajoa.")
    try:
        keywords = normalize_keywords(profile.keywords)
    except (TypeError, ValueError) as exc:
        raise ValueError("Relevanssin hakuprofiilin kiinnostavat hakusanat eivät ole käyttökelpoisia.") from exc
    if not keywords:
        raise ValueError(
            "Relevanssin hakuprofiilissa ei ole kiinnostavia hakusanoja; "
            "tyhjää profiilia ei voi käyttää ilmoitusten arviointiin."
        )


def _next_run_text(next_run_at: datetime) -> str:
    if next_run_at.tzinfo is None or next_run_at.utcoffset() is None:
        raise ValueError("Seuraavan hakuajan pitää sisältää aikavyöhyke.")
    return next_run_at.strftime("%d.%m.%Y klo %H:%M %Z")


def _source_name(source: str) -> str:
    return {
        "EURA": "EURA 2021",
        "HAEAVUSTUKSIA": "Haeavustuksia.fi",
    }.get(source, source)


def _message(calls: list[FundingCall], next_run_at: datetime) -> NotificationEmail:
    recipient = config.NOTIFICATION_EMAIL_TO
    if calls:
        sections = ["Uusia mahdollisesti sopivia rahoitushakuja löytyi."]
        for call in calls:
            detail_url = call.source_url or _source_url(call)
            sections.append(
                "\n".join((
                    f"Nimi: {call.title}",
                    f"Rahoituslähde: {call.fund or 'Ei tiedossa'}",
                    f"Lähde: {_source_name(call.source)}",
                    f"Kuvaus: {call.description or 'Kuvausta ei ole saatavilla.'}",
                    f"Lisätiedot: {detail_url or 'Linkkiä ei ole saatavilla.'}",
                ))
            )
        return NotificationEmail(
            recipient=recipient,
            subject="Uusia potentiaalisia hankkeita löytyi",
            body="\n\n".join(sections),
        )

    return NotificationEmail(
        recipient=recipient,
        subject="Ei uusia potentiaalisia hankkeita",
        body=(
            "Ajastettu haku on suoritettu molemmille nykyisille lähteille "
            "(Haeavustuksia.fi ja EURA 2021), eikä uusia sopiviksi arvioituja hankkeita löytynyt.\n"
            f"Seuraava haku: {_next_run_text(next_run_at)}."
        ),
    )


def _history_for_run(session: Session, run_id: int) -> list[NotificationHistory]:
    return list(session.scalars(
        select(NotificationHistory)
        .where(NotificationHistory.run_id == run_id)
        .order_by(NotificationHistory.id)
    ))


def _run_result(session: Session, run: NotificationRun) -> NotificationRunResult:
    histories = _history_for_run(session, run.id)
    email = None
    if run.subject is not None and run.body is not None:
        email = NotificationEmail(
            recipient=config.NOTIFICATION_EMAIL_TO,
            subject=run.subject,
            body=run.body,
        )
    return NotificationRunResult(
        run_key=run.run_key,
        status=run.status,
        notified_call_ids=tuple(
            item.funding_call_id for item in histories if item.status == "SENT"
        ),
        email=email,
    )


def _record_error(session: Session, run_id: int, message: str) -> None:
    run = session.get(NotificationRun, run_id)
    if run is not None:
        run.last_error = message[:4000]
        session.commit()


def _get_or_create_run(session: Session, run_key: str, next_run_at: datetime) -> NotificationRun:
    if not run_key.strip():
        raise ValueError("Ilmoitusajolle pitää antaa pysyvä run_key.")
    if next_run_at.tzinfo is None or next_run_at.utcoffset() is None:
        raise ValueError("Seuraavan hakuajan pitää sisältää aikavyöhyke.")
    run = session.scalar(select(NotificationRun).where(NotificationRun.run_key == run_key))
    if run is not None:
        return run
    run = NotificationRun(
        run_key=run_key,
        status="IMPORTING",
        phase="import",
        next_run_at=next_run_at.isoformat(),
    )
    session.add(run)
    session.commit()
    return run


def _evaluate_run(session: Session, run: NotificationRun, minimum_score: int) -> None:
    try:
        _validate_profile(session)
        pending = _history_for_run(session, run.id)
        pending_ids = [
            item.funding_call_id for item in pending if item.status == "PENDING_EVALUATION"
        ]
        # Empty ids still exercises the scorer's active-profile validation.
        score_funding_calls(session, call_ids=pending_ids, include_ended=True)
    except Exception as exc:
        session.rollback()
        _record_error(session, run.id, str(exc))
        raise

    pending = [
        item for item in _history_for_run(session, run.id)
        if item.status == "PENDING_EVALUATION"
    ]
    call_ids = [item.funding_call_id for item in pending]
    calls_by_id = {}
    if call_ids:
        calls_by_id = {
            call.id: call
            for call in session.scalars(
                select(FundingCall)
                .join(FundingCall.evaluation)
                .where(FundingCall.id.in_(call_ids))
            )
        }
    selected: list[FundingCall] = []
    for item in pending:
        call = calls_by_id[item.funding_call_id]
        if call.evaluation.suitability_score is not None and call.evaluation.suitability_score >= minimum_score:
            item.status = "READY"
            selected.append(call)
        else:
            item.status = "NOT_SELECTED"

    message = _message(selected, datetime.fromisoformat(run.next_run_at))
    run.status = "READY"
    run.phase = "send"
    run.subject = message.subject
    run.body = message.body
    run.last_error = None
    session.commit()


def mark_interrupted_notification(
    session: Session,
    run_key: str,
    *,
    expected_attempt_at: datetime,
) -> NotificationRunResult:
    """Mark an attempt uncertain only after confirming its sender is no longer active.

    There is deliberately no timeout-based recovery: a slow sender must not be treated as
    interrupted. The persisted attempt timestamp guards against resolving a newer attempt.
    """
    run = session.scalar(select(NotificationRun).where(NotificationRun.run_key == run_key))
    if run is None or run.status != "ATTEMPTING":
        raise ValueError("Run is not in ATTEMPTING state.")
    if run.last_attempt_at != expected_attempt_at:
        raise ValueError("Attempt timestamp no longer matches the run.")
    result = session.execute(
        update(NotificationRun)
        .where(
            NotificationRun.id == run.id,
            NotificationRun.status == "ATTEMPTING",
            NotificationRun.last_attempt_at == expected_attempt_at,
        )
        .values(
            status="UNCERTAIN",
            last_error="Sender was confirmed stopped; delivery outcome is unknown.",
        )
    )
    if result.rowcount != 1:
        session.rollback()
        raise ValueError("Run state changed while recovering the interrupted attempt.")
    for item in _history_for_run(session, run.id):
        if item.status == "ATTEMPTING":
            item.status = "UNCERTAIN"
            item.last_error = "Sender was confirmed stopped; delivery outcome is unknown."
    session.commit()
    return _run_result(session, session.get(NotificationRun, run.id))


def resolve_uncertain_notification(
    session: Session,
    run_key: str,
    *,
    delivered: bool,
) -> NotificationRunResult:
    """Resolve an uncertain delivery only after checking the mail provider or recipient."""
    run = session.scalar(select(NotificationRun).where(NotificationRun.run_key == run_key))
    if run is None or run.status != "UNCERTAIN":
        raise ValueError("Ilmoitusajoa ei löydy epäselvässä lähetys-/toimitustilassa.")
    if delivered:
        resolved_status = "SENT"
        run.sent_at = datetime.now(timezone.utc)
        run.last_error = None
    else:
        resolved_status = "FAILED"
        run.last_error = "Käyttäjä vahvisti, ettei viestiä toimitettu."
    run.status = resolved_status
    for item in _history_for_run(session, run.id):
        if item.status == "UNCERTAIN":
            item.status = resolved_status
            item.last_error = run.last_error
            if delivered:
                item.sent_at = run.sent_at
    session.commit()
    return _run_result(session, run)


def run_notification(
    session: Session,
    sender: NotificationSender,
    *,
    run_key: str,
    next_run_at: datetime,
    client: httpx.Client | None = None,
    retry_failed: bool = False,
) -> NotificationRunResult:
    """Run or resume a persisted notification execution.

    run_key must be stable across retries of the same logical run. Sends that may have
    succeeded are never retried automatically. A transport must report definite non-delivery
    explicitly with NotificationSendError(outcome_unknown=False).
    """
    run = _get_or_create_run(session, run_key, next_run_at)

    if run.status == "SENT":
        return _run_result(session, run)
    if run.status == "UNCERTAIN":
        raise NotificationDeliveryUncertain(
            f"Ilmoitusajon {run_key} lähetys jäi epäselväksi; sitä ei yritetä automaattisesti uudelleen."
        )
    if run.status == "ATTEMPTING":
        raise NotificationRunInProgress(
            f"Ilmoitusajo {run_key} has an active or unresolved sender reservation. "
            "Confirm the sender has stopped before explicitly recovering the attempt."
        )
    if run.status == "FAILED":
        if not retry_failed:
            raise NotificationRunFailed(
                f"Ilmoitusajon {run_key} lähetys epäonnistui varmasti; käytä retry_failed=True uuteen yritykseen."
            )
        run.status = "READY"
        run.last_error = None
        for item in _history_for_run(session, run.id):
            if item.status == "FAILED":
                item.status = "READY"
                item.last_error = None
        session.commit()

    minimum_score = None
    if run.status in ("IMPORTING", "EVALUATING"):
        try:
            minimum_score = _minimum_score()
        except Exception as exc:
            _record_error(session, run.id, str(exc))
            raise

    if run.status == "IMPORTING":
        try:
            _validate_profile(session)
        except Exception as exc:
            _record_error(session, run.id, str(exc))
            raise
        try:
            run_imports(
                session,
                client,
                include_created_ids=True,
                notification_run_id=run.id,
            )
        except Exception as exc:
            session.rollback()
            _record_error(session, run.id, str(exc))
            raise
        run = session.get(NotificationRun, run.id)

    if run.status == "EVALUATING":
        assert minimum_score is not None
        _evaluate_run(session, run, minimum_score)
        run = session.get(NotificationRun, run.id)

    if run.status == "READY":
        histories = _history_for_run(session, run.id)
        attempt_time = datetime.now(timezone.utc)
        claimed = session.execute(
            update(NotificationRun)
            .where(NotificationRun.id == run.id, NotificationRun.status == "READY")
            .values(
                status="ATTEMPTING",
                attempt_count=NotificationRun.attempt_count + 1,
                last_attempt_at=attempt_time,
            )
        )
        if claimed.rowcount != 1:
            session.rollback()
            current = session.get(NotificationRun, run.id)
            if current is not None and current.status in ("ATTEMPTING", "UNCERTAIN"):
                raise NotificationRunInProgress(
                    f"Ilmoitusajo {run_key} on jo lähetysyrityksessä tai sen tulos on epäselvä."
                )
            if current is not None and current.status == "SENT":
                return _run_result(session, current)
            raise NotificationRunFailed(f"Ilmoitusajoa {run_key} ei voitu varata lähetykseen.")
        for item in histories:
            if item.status == "READY":
                item.status = "ATTEMPTING"
        session.commit()
        run = session.get(NotificationRun, run.id)

        message = NotificationEmail(
            recipient=config.NOTIFICATION_EMAIL_TO,
            subject=run.subject or "",
            body=run.body or "",
        )
        try:
            sender.send(message)
        except Exception as exc:
            outcome_unknown = not isinstance(exc, NotificationSendError) or exc.outcome_unknown
            failure_status = "UNCERTAIN" if outcome_unknown else "FAILED"
            failure_message = str(exc)[:4000]
            failed = session.execute(
                update(NotificationRun)
                .where(
                    NotificationRun.id == run.id,
                    NotificationRun.status == "ATTEMPTING",
                    NotificationRun.last_attempt_at == attempt_time,
                )
                .values(status=failure_status, last_error=failure_message)
            )
            if failed.rowcount != 1:
                session.rollback()
                raise NotificationDeliveryUncertain(
                    f"Ilmoitusajon {run_key} tila muuttui lähetyksen aikana; tarkista toimitus."
                ) from exc
            for item in _history_for_run(session, run.id):
                if item.status == "ATTEMPTING":
                    item.status = failure_status
                    item.last_error = failure_message
            session.commit()
            if outcome_unknown:
                raise NotificationDeliveryUncertain(
                    f"Ilmoitusajon {run_key} lähetys saattoi onnistua; automaattista uusintaa ei tehdä."
                ) from exc
            raise

        sent_at = datetime.now(timezone.utc)
        completed = session.execute(
            update(NotificationRun)
            .where(
                NotificationRun.id == run.id,
                NotificationRun.status == "ATTEMPTING",
                NotificationRun.last_attempt_at == attempt_time,
            )
            .values(status="SENT", sent_at=sent_at, last_error=None)
        )
        if completed.rowcount != 1:
            session.rollback()
            raise NotificationDeliveryUncertain(
                f"Ilmoitusajon {run_key} tila muuttui lähetyksen aikana; tarkista toimitus ennen uusintaa."
            )
        for item in _history_for_run(session, run.id):
            if item.status == "ATTEMPTING":
                item.status = "SENT"
                item.sent_at = sent_at
                item.last_error = None
        session.commit()
        run = session.get(NotificationRun, run.id)

    return _run_result(session, run)
