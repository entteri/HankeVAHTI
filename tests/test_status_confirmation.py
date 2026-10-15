from datetime import datetime
from unittest.mock import ANY, Mock

import pytest
from nicegui import events, ui

from app.models import EvaluationStatus, Participation
from app.services.funding_calls import set_funding_call_status
from app.ui.funding_calls import STATUS_LABELS
from tests.test_funding_call_sorting import _add_call
from tests.test_funding_calls import _test_client
from tests.test_relevance_ui import _click, _page_client


DECISIONS = [
    ("Osallistu", EvaluationStatus.NEW, EvaluationStatus.PARTICIPATE),
    ("Hylkää", EvaluationStatus.PARTICIPATE, EvaluationStatus.REJECTED),
    ("Arvioimatta", EvaluationStatus.REJECTED, EvaluationStatus.NEW),
]


@pytest.mark.parametrize("action,initial,target", DECISIONS)
def test_status_requires_confirmation_and_cancel_preserves_data(db_session, monkeypatch, action, initial, target):
    other = _add_call(db_session, "Toinen haku", status=initial)
    call = _add_call(db_session, "Vahvistettava haku", 80, status=initial)
    call.evaluation.ai_summary = "Tallennettu soveltuvuusarvio"
    call.evaluation.matched_keywords = ["koulutus"]
    if initial is EvaluationStatus.REJECTED:
        call.evaluation.rejected_at = datetime(2026, 10, 10, 12, 0)
    if initial is EvaluationStatus.PARTICIPATE:
        call.participation = Participation(notes="Säilytettävä muistiinpano")
    db_session.commit()
    save = Mock(wraps=set_funding_call_status)
    monkeypatch.setattr("app.ui.funding_calls.set_funding_call_status", save)

    with _test_client(db_session, monkeypatch) as client:
        before = client.get(f"/api/funding-calls/{call.id}").json()
        other_before = client.get(f"/api/funding-calls/{other.id}").json()
        page = _page_client(client.get("/hankkeet"))
        confirmation = next(e for e in page.elements.values() if isinstance(e, ui.dialog))
        assert not confirmation.value
        client.portal.call(_click, page, action)
        assert confirmation.value
        labels = [e.text for e in page.elements.values() if isinstance(e, ui.label)]
        assert "Vahvista tilan muutos" in labels
        assert call.title in labels
        assert f"Tila: {STATUS_LABELS[initial]} → {STATUS_LABELS[target]}" in labels
        assert client.get(f"/api/funding-calls/{call.id}").json() == before
        save.assert_not_called()

        client.portal.call(_click, page, "Peruuta")
        assert not confirmation.value
        assert client.get(f"/api/funding-calls/{call.id}").json() == before
        client.portal.call(_click, page, "Vahvista")  # A stale event after cancellation does nothing.
        save.assert_not_called()

        client.portal.call(_click, page, action)
        client.portal.call(_click, page, "Vahvista")
        assert not confirmation.value
        saved = client.get(f"/api/funding-calls/{call.id}").json()
        assert saved["status"] == target.value
        assert bool(saved["rejected_at"]) is (target is EvaluationStatus.REJECTED)
        assert saved["suitability_score"] == 80
        assert saved["ai_summary"] == before["ai_summary"]
        assert saved["matched_keywords"] == before["matched_keywords"]
        db_session.expire_all()
        notes = call.participation.notes if call.participation else None
        assert notes == ("Säilytettävä muistiinpano" if initial is EvaluationStatus.PARTICIPATE else None)
        assert client.get(f"/api/funding-calls/{other.id}").json() == other_before
        client.portal.call(_click, page, "Vahvista")  # No duplicate save on a second click.
        save.assert_called_once_with(ANY, call.id, target)


def _dismiss(page, dialog):
    """The hide event is also emitted when dismissed by Escape or backdrop."""
    with page:
        dialog.close()
        listener = next(e for e in dialog._event_listeners.values() if e.type == "hide")
        events.handle_event(listener.handler, events.GenericEventArguments(sender=dialog, client=page, args=None))


@pytest.mark.parametrize("action,initial,target", DECISIONS)
def test_dismissing_confirmation_does_not_save(db_session, monkeypatch, action, initial, target):
    call = _add_call(db_session, "Suljettava vahvistus", status=initial)
    db_session.commit()
    save = Mock(wraps=set_funding_call_status)
    monkeypatch.setattr("app.ui.funding_calls.set_funding_call_status", save)
    with _test_client(db_session, monkeypatch) as client:
        before = client.get(f"/api/funding-calls/{call.id}").json()
        page = _page_client(client.get("/hankkeet"))
        client.portal.call(_click, page, action)
        dialog = next(e for e in page.elements.values() if isinstance(e, ui.dialog) and e.value)
        client.portal.call(_dismiss, page, dialog)
        client.portal.call(_click, page, "Vahvista")
        save.assert_not_called()
        assert client.get(f"/api/funding-calls/{call.id}").json() == before
