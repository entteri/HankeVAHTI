from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from nicegui import ui

from app.models import Evaluation, EvaluationStatus, FundingCall
from app.services.funding_calls import set_funding_call_status
from app.ui.funding_calls import _rejected_at
from tests.test_funding_calls import _test_client
from tests.test_relevance_ui import _page_client


@pytest.mark.parametrize("initial", [None, EvaluationStatus.NEW, EvaluationStatus.INTERESTING])
def test_rejection_records_utc_time_including_new_evaluation(db_session, monkeypatch, initial):
    call = FundingCall(source="EURA", source_id="1", title="Haku")
    if initial is not None:
        call.evaluation = Evaluation(status=initial)
    db_session.add(call)
    db_session.commit()
    now = datetime(2026, 10, 8, 6, 34, tzinfo=timezone.utc)
    clock = Mock()
    clock.now.return_value = now
    monkeypatch.setattr("app.services.funding_calls.datetime", clock)
    result = set_funding_call_status(db_session, call.id, EvaluationStatus.REJECTED)
    assert result.status is EvaluationStatus.REJECTED
    assert result.rejected_at.replace(tzinfo=timezone.utc) == now
    clock.now.assert_called_once_with(timezone.utc)


@pytest.mark.parametrize("restored", [s for s in EvaluationStatus if s is not EvaluationStatus.REJECTED])
def test_reset_clears_timestamp_and_rejection_gets_new_time(db_session, monkeypatch, restored):
    call = FundingCall(source="EURA", source_id="1", title="Haku", evaluation=Evaluation(status=EvaluationStatus.NEW))
    db_session.add(call)
    db_session.commit()
    first = datetime(2026, 10, 8, 6, 34, tzinfo=timezone.utc)
    second = datetime(2026, 10, 9, 7, 45, tzinfo=timezone.utc)
    clock = Mock()
    clock.now.side_effect = [first, second]
    monkeypatch.setattr("app.services.funding_calls.datetime", clock)
    rejected = set_funding_call_status(db_session, call.id, EvaluationStatus.REJECTED)
    repeated = set_funding_call_status(db_session, call.id, EvaluationStatus.REJECTED)
    assert repeated.rejected_at == rejected.rejected_at
    assert set_funding_call_status(db_session, call.id, restored).rejected_at is None
    again = set_funding_call_status(db_session, call.id, EvaluationStatus.REJECTED)
    assert again.rejected_at.replace(tzinfo=timezone.utc) == second
    assert again.rejected_at != rejected.rejected_at
    assert clock.now.call_count == 2


def test_legacy_rejection_never_uses_updated_at(db_session):
    call = FundingCall(source="EURA", source_id="1", title="Vanha",
                       evaluation=Evaluation(status=EvaluationStatus.REJECTED))
    db_session.add(call)
    db_session.commit()
    assert call.evaluation.updated_at is not None
    assert set_funding_call_status(db_session, call.id, EvaluationStatus.REJECTED).rejected_at is None


def test_other_evaluation_updates_leave_rejection_time_unchanged(db_session):
    call = FundingCall(source="EURA", source_id="1", title="Haku")
    db_session.add(call)
    db_session.commit()
    before = set_funding_call_status(db_session, call.id, EvaluationStatus.REJECTED).rejected_at
    call.evaluation.suitability_score = 60
    call.evaluation.suitability_summary = "Uusi perustelu"
    call.evaluation.matched_keywords = ["koulutus"]
    call.evaluation.matched_excluded_keywords = []
    call.evaluation.ai_summary = "Uusi AI-yhteenveto"
    db_session.commit()
    db_session.refresh(call.evaluation)
    assert call.evaluation.rejected_at == before


@pytest.mark.parametrize("timestamp,expected", [
    (datetime(2026, 10, 8, 6, 34, tzinfo=timezone.utc), "08.10.2026 klo 09:34"),
    (datetime(2026, 1, 8, 6, 34), "08.01.2026 klo 08:34"),
    (None, "Ei tiedossa"),
])
def test_ui_rejection_time_in_card_and_details(db_session, monkeypatch, timestamp, expected):
    assert _rejected_at(timestamp) == expected
    call = FundingCall(source="EURA", source_id="1", title="Hylätty haku",
                       evaluation=Evaluation(status=EvaluationStatus.REJECTED, rejected_at=timestamp))
    db_session.add(call)
    db_session.commit()
    with _test_client(db_session, monkeypatch) as client:
        page = _page_client(client.get("/hylatyt"))
        labels = [e.text for e in page.elements.values() if isinstance(e, ui.label)]
        assert labels.count(f"Hylätty: {expected}") == 2
        payload = client.get(f"/api/funding-calls/{call.id}").json()
        assert (payload["rejected_at"] is None) == (timestamp is None)
        client.patch(f"/api/funding-calls/{call.id}/status", json={"status": "NEW"})
        page = _page_client(client.get("/arvioi"))
        assert not any(e.text.startswith("Hylätty:") for e in page.elements.values() if isinstance(e, ui.label))
