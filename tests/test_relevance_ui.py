"""Sivujen sekä niiden oikeiden tallennus- ja pisteytyskäsittelijöiden testit."""

import asyncio
import re

import pytest
from fastapi.testclient import TestClient
from nicegui import Client, events, ui
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models import EvaluationStatus, FundingCall, SearchProfile
from app.services.search_profiles import get_keyword_settings, save_keyword_settings
from tests.test_funding_calls import _test_client


def _page_client(response) -> Client:
    assert response.status_code == 200
    client_id = re.search(r"'client_id': '([0-9a-f-]+)'", response.text).group(1)
    return Client.instances[client_id]


async def _click(client: Client, text: str) -> None:
    """Kutsu sivun rekisteröimää käsittelijää NiceGUI:n asiakaskontekstissa."""
    button = next(e for e in client.elements.values() if isinstance(e, ui.button) and e.text == text)
    assert button.enabled
    with client:
        listener = next(e for e in button._event_listeners.values() if e.type == "click")
        before = asyncio.all_tasks()
        events.handle_event(listener.handler, events.GenericEventArguments(sender=button, client=client, args=None))
        pending = asyncio.all_tasks() - before
        if pending:
            await asyncio.wait_for(asyncio.gather(*pending), timeout=5)


def _edit(client: Client, label: str, value: str) -> None:
    with client:
        element = next(e for e in client.elements.values() if isinstance(e, ui.textarea) and e.props["label"] == label)
        element.set_value(value)


def test_settings_save_reload_score_and_display_in_list_and_details(db_session, monkeypatch):
    call = FundingCall(source="EURA", source_id="test-1", title="Koulutus ja tekoäly", description="Digitaidot ja osallisuus")
    db_session.add(call)
    db_session.commit()
    call_id = call.id
    monkeypatch.setattr("app.ui.settings.SessionLocal", sessionmaker(bind=db_session.get_bind()))
    with _test_client(db_session, monkeypatch) as client:
        page = _page_client(client.get("/asetukset"))
        assert db_session.scalar(select(func.count()).select_from(SearchProfile)) == 0
        client.portal.call(_edit, page, "Kiinnostavat hakusanat", "koulutus\ntekoäly\ndigitaidot\nosallisuus")
        client.portal.call(_edit, page, "Poissulkusanat", "rakentaminen")
        client.portal.call(_click, page, "Tallenna hakusanat")
        db_session.expire_all()
        assert get_keyword_settings(db_session).keywords == ("koulutus", "tekoäly", "digitaidot", "osallisuus")
        reloaded = _page_client(client.get("/asetukset"))
        fields = [e.value for e in reloaded.elements.values() if isinstance(e, ui.textarea)]
        assert "koulutus\ntekoäly\ndigitaidot\nosallisuus" in fields
        assert "rakentaminen" in fields
        client.portal.call(_click, reloaded, "Pisteytä päättymättömät haut")
        details = client.get(f"/api/funding-calls/{call_id}").json()
        assert details["suitability_score"] == 80
        assert details["status"] == "NEW"
        response = client.get("/arvioi")
        assert "Relevanssi: 80 / 100" in response.text
        assert "Hyvin relevantti" in response.text
        assert "Relevanssianalyysi" in response.text
        assert "Osuvat hakusanat (4): koulutus, tekoäly, digitaidot, osallisuus" in response.text
        assert "Poissulkevat osumat (0): ei osumia" in response.text
        assert "Osallistu" in response.text
        assert "Hylkää" in response.text
        client.portal.call(_edit, reloaded, "Kiinnostavat hakusanat", "")
        client.portal.call(_edit, reloaded, "Poissulkusanat", "")
        client.portal.call(_click, reloaded, "Tallenna hakusanat")
        assert client.get(f"/api/funding-calls/{call_id}").json()["suitability_score"] == 80
        client.portal.call(_click, reloaded, "Pisteytä päättymättömät haut")
        assert client.get(f"/api/funding-calls/{call_id}").json()["suitability_score"] == 0
        assert "Todennäköisesti ei relevantti" in client.get("/hankkeet").text
    db_session.expire_all()
    assert get_keyword_settings(db_session).keywords == ()
    assert get_keyword_settings(db_session).excluded_keywords == ()
    assert db_session.get(FundingCall, call_id).evaluation.status is EvaluationStatus.NEW


@pytest.mark.parametrize("saved", [False, True])
def test_scoring_button_recovers_when_profile_missing_or_scoring_fails(db_session, monkeypatch, saved):
    monkeypatch.setattr("app.ui.settings.SessionLocal", sessionmaker(bind=db_session.get_bind()))
    if saved:
        save_keyword_settings(db_session, ["koulutus"], [])

        def fail(session):
            raise RuntimeError("Testivirhe")

        monkeypatch.setattr("app.ui.settings.score_funding_calls", fail)
    with TestClient(app) as client:
        page = _page_client(client.get("/asetukset"))
        client.portal.call(_click, page, "Pisteytä päättymättömät haut")
        labels = [e.text for e in page.elements.values() if isinstance(e, ui.label)]
        expected = ("Pisteytys epäonnistui. Aiemmat tulokset säilytettiin." if saved else
                    "Tallenna relevanssin hakusanat Asetukset-sivulla ennen pisteytystä.")
        assert expected in labels
        buttons = [e for e in page.elements.values() if isinstance(e, ui.button)
                   and e.text in {"Tallenna hakusanat", "Pisteytä päättymättömät haut"}]
        assert all(button.enabled for button in buttons)


def test_unscored_call_shows_no_score_instead_of_zero(db_session, monkeypatch):
    db_session.add(FundingCall(source="EURA", source_id="1", title="Arvioimaton haku"))
    db_session.commit()
    with _test_client(db_session, monkeypatch) as client:
        response = client.get("/hankkeet")
    assert "Relevanssi: Ei vielä pisteytetty" in response.text
    assert "Relevanssi: 0 / 100" not in response.text
