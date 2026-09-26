import json
from datetime import date
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from google.genai import errors, types
from nicegui import ui

from app.core import config
from app.models import Evaluation, EvaluationStatus, FundingCall, Participation
from app.services.funding_calls import get_funding_call
from app.services.gemini import GeminiError, SYSTEM_INSTRUCTION, ask_gemini
from app.ui.ai_assistant import PRESET_QUESTIONS
from tests.test_funding_calls import _test_client
from tests.test_relevance_ui import _click, _edit, _page_client


@pytest.fixture(autouse=True)
def sdk(monkeypatch):
    """Kaikki tämän moduulin testit korvaavat SDK-clientin, myös UI-testit."""
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-only-key")
    monkeypatch.setattr(config, "GEMINI_MODEL", "test-only-model")
    factory = MagicMock()
    client = factory.return_value.__enter__.return_value
    client.models.generate_content.return_value = SimpleNamespace(text="Faktat: koulutushaku. Ehdotus: pilotti. Tarkista hakukelpoisuus.")
    monkeypatch.setattr("app.services.gemini.genai.Client", factory)
    return factory, client


@pytest.fixture
def funding_call(db_session):
    call = FundingCall(
        source="EURA", source_id="test-call", title="Koulutus ja tekoäly",
        description="Kehitetään digitaalisia oppimisympäristöjä.", fund="ESR+", category="4.2",
        application_start_date=date(2026, 9, 1), application_end_date=date(2026, 12, 31),
        raw_data={"private": "raw-data-must-not-leak"},
    )
    call.evaluation = Evaluation(status=EvaluationStatus.PARTICIPATE, suitability_score=80, suitability_summary="Hakusanat: koulutus, tekoäly.")
    call.participation = Participation(notes="private-notes", responsible_person="private-person", next_action="private-action")
    db_session.add(call)
    db_session.commit()
    return get_funding_call(db_session, call.id)


def test_question_context_model_and_system_instruction_are_sent_without_private_fields(funding_call, sdk):
    factory, client = sdk
    assert "Faktat:" in ask_gemini(funding_call, "  Miten kehittää hankeidea?  ")
    factory.assert_called_once()
    assert factory.call_args.kwargs["api_key"] == "test-only-key"
    assert factory.call_args.kwargs["vertexai"] is False
    options = factory.call_args.kwargs["http_options"]
    assert options.timeout == 60_000
    assert options.retry_options.attempts == 1
    sent = client.models.generate_content.call_args.kwargs
    assert sent["model"] == "test-only-model"
    assert sent["config"].system_instruction == SYSTEM_INSTRUCTION
    assert sent["config"].tools is None
    assert "Suomen eOppimiskeskuksen" in sent["config"].system_instruction
    assert json.loads(sent["contents"]) == {
        "question": "Miten kehittää hankeidea?",
        "funding_call": {
            "title": funding_call.title,
            "description": funding_call.description,
            "source": "EURA",
            "fund": "ESR+",
            "category": "4.2",
            "application_start_date": "2026-09-01",
            "application_end_date": "2026-12-31",
            "suitability_score": 80,
            "suitability_summary": "Hakusanat: koulutus, tekoäly.",
        },
    }
    factory.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize("key,model,missing", [
    ("", "test-only-model", "GEMINI_API_KEY"),
    ("test-only-key", "", "GEMINI_MODEL"),
    ("", "", "GEMINI_API_KEY ja GEMINI_MODEL"),
])
def test_missing_configuration_is_clear_and_does_not_create_client(funding_call, sdk, monkeypatch, key, model, missing):
    monkeypatch.setattr(config, "GEMINI_API_KEY", key)
    monkeypatch.setattr(config, "GEMINI_MODEL", model)
    with pytest.raises(GeminiError, match=missing):
        ask_gemini(funding_call, "Kysymys")
    sdk[0].assert_not_called()


def test_blank_question_is_not_sent(funding_call, sdk):
    with pytest.raises(GeminiError, match="Kirjoita kysymys"):
        ask_gemini(funding_call, "  \n  ")
    sdk[0].assert_not_called()


@pytest.mark.parametrize("error,message", [
    (httpx.ConnectError("sensitive details"), "verkkoyhteyttä"),
    (httpx.ReadTimeout("sensitive details"), "aikakatkaistiin"),
    (errors.ClientError(429, {"error": {"message": "sensitive details"}}), "käyttöraja"),
    (errors.ClientError(401, {"error": {"message": "sensitive details"}}), "käyttöoikeutta"),
    (errors.ClientError(403, {"error": {"message": "sensitive details"}}), "käyttöoikeutta"),
    (errors.ClientError(403, {"error": {"message": "Your project has been denied access. Please contact support. sensitive details"}}), "Google on estänyt tämän projektin"),
    (errors.ClientError(404, {"error": {"message": "sensitive details"}}), "mallia ei löytynyt"),
    (errors.ClientError(400, {"error": {"message": "sensitive details"}}), "API-virhe"),
    (errors.ServerError(503, {"error": {"message": "sensitive details"}}), "API-virhe"),
    (RuntimeError("sensitive details"), "pyyntö epäonnistui"),
])
def test_errors_are_safe_finnish_messages_and_client_is_closed(funding_call, sdk, caplog, error, message):
    factory, client = sdk
    client.models.generate_content.side_effect = error
    with pytest.raises(GeminiError, match=message) as caught:
        ask_gemini(funding_call, "Kysymys")
    assert "sensitive details" not in str(caught.value) + caplog.text
    assert "test-only-key" not in str(caught.value) + caplog.text
    factory.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize("response", [SimpleNamespace(text="  "), types.GenerateContentResponse()])
def test_empty_or_blocked_response_is_handled(funding_call, sdk, response):
    sdk[1].models.generate_content.return_value = response
    with pytest.raises(GeminiError, match="ei palauttanut tekstivastausta"):
        ask_gemini(funding_call, "Kysymys")


def test_client_creation_failure_is_handled(funding_call, sdk):
    sdk[0].side_effect = httpx.ConnectError("sensitive details")
    with pytest.raises(GeminiError, match="verkkoyhteyttä"):
        ask_gemini(funding_call, "Kysymys")


def test_missing_context_fields_remain_unknown(db_session, sdk):
    call = FundingCall(source="HAEAVUSTUKSIA", source_id="minimal", title="Vain nimi")
    db_session.add(call)
    db_session.commit()
    ask_gemini(get_funding_call(db_session, call.id), "Mitä puuttuu?")
    context = json.loads(sdk[1].models.generate_content.call_args.kwargs["contents"])["funding_call"]
    assert context["description"] is None
    assert context["application_end_date"] is None
    assert context["suitability_score"] is None


def _open_assistant(client):
    page = _page_client(client.get("/hankkeet"))
    client.portal.call(_click, page, "Lisätiedot")
    client.portal.call(_click, page, "AI-sparraaja")
    return page


def _labels(page):
    return [element.text for element in page.elements.values() if isinstance(element, ui.label)]


def test_ui_opens_without_key_and_existing_app_still_works(db_session, monkeypatch, funding_call, sdk):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GEMINI_MODEL", "")
    with _test_client(db_session, monkeypatch) as client:
        assert client.get("/health").json() == {"status": "ok"}
        page = _open_assistant(client)
        assert any("GEMINI_API_KEY ja GEMINI_MODEL" in text for text in _labels(page))
        assert funding_call.title in _labels(page)
        for label in ["Lähetä", *PRESET_QUESTIONS]:
            assert any(isinstance(e, ui.button) and e.text == label for e in page.elements.values())
        client.portal.call(_edit, page, "Kysymyksesi", "Kysymys")
        client.portal.call(_click, page, "Lähetä")
        sdk[0].assert_not_called()
        assert client.get("/hankkeet").status_code == 200


def test_ui_sends_and_displays_answer_without_database_changes(db_session, monkeypatch, funding_call, sdk):
    before = get_funding_call(db_session, funding_call.id)
    with _test_client(db_session, monkeypatch) as client:
        page = _open_assistant(client)
        sdk[0].assert_not_called()  # Avaaminen ei tee maksullista pyyntöä.
        client.portal.call(_edit, page, "Kysymyksesi", "Mikä on tavoite?")
        client.portal.call(_click, page, "Lähetä")
        sent = json.loads(sdk[1].models.generate_content.call_args.kwargs["contents"])
        assert sent["question"] == "Mikä on tavoite?"
        assert sent["funding_call"]["title"] == funding_call.title
        assert "Vastaus valmis." in _labels(page)
        assert sdk[1].models.generate_content.return_value.text in _labels(page)
    db_session.expire_all()
    assert get_funding_call(db_session, funding_call.id) == before
    stored = db_session.get(FundingCall, funding_call.id)
    assert stored.raw_data == {"private": "raw-data-must-not-leak"}
    assert stored.participation.notes == "private-notes"


@pytest.mark.parametrize("label", list(PRESET_QUESTIONS))
def test_preset_buttons_send_their_question(db_session, monkeypatch, funding_call, sdk, label):
    with _test_client(db_session, monkeypatch) as client:
        page = _open_assistant(client)
        client.portal.call(_click, page, label)
    sent = json.loads(sdk[1].models.generate_content.call_args.kwargs["contents"])
    assert sent["question"] == PRESET_QUESTIONS[label]


def test_ui_recovers_after_api_error_and_allows_retry(db_session, monkeypatch, funding_call, sdk):
    sdk[1].models.generate_content.side_effect = errors.ServerError(503, {"error": {"message": "sensitive details"}})
    with _test_client(db_session, monkeypatch) as client:
        page = _open_assistant(client)
        client.portal.call(_edit, page, "Kysymyksesi", "Kysymys")
        client.portal.call(_click, page, "Lähetä")
        assert any("API-virhe" in text for text in _labels(page))
        assert not any("sensitive details" in text for text in _labels(page))
        send = next(e for e in page.elements.values() if isinstance(e, ui.button) and e.text == "Lähetä")
        assert send.enabled
        sdk[1].models.generate_content.side_effect = None
        client.portal.call(_click, page, "Lähetä")
        assert "Vastaus valmis." in _labels(page)


def test_ui_does_not_send_empty_question(db_session, monkeypatch, funding_call, sdk):
    with _test_client(db_session, monkeypatch) as client:
        page = _open_assistant(client)
        client.portal.call(_edit, page, "Kysymyksesi", "  ")
        client.portal.call(_click, page, "Lähetä")
        assert "Kirjoita kysymys tai valitse valmis toiminto." in _labels(page)
        sdk[0].assert_not_called()


def test_ui_remains_responsive_and_disables_send_controls_during_request(db_session, monkeypatch, funding_call, sdk):
    started = Event()
    release = Event()

    def slow_response(**kwargs):
        started.set()
        assert release.wait(timeout=4)
        return SimpleNamespace(text="Valmis vastaus")

    sdk[1].models.generate_content.side_effect = slow_response
    with _test_client(db_session, monkeypatch) as client:
        page = _open_assistant(client)
        client.portal.call(_edit, page, "Kysymyksesi", "Kysymys")
        pending = client.portal.start_task_soon(_click, page, "Lähetä")
        try:
            assert started.wait(timeout=2)
            buttons = [e for e in page.elements.values() if isinstance(e, ui.button)
                       and e.text in {"Lähetä", *PRESET_QUESTIONS}]
            assert len(buttons) == 5
            assert all(not button.enabled for button in buttons)
            assert client.get("/health").status_code == 200
            sdk[1].models.generate_content.assert_called_once()
        finally:
            release.set()
            pending.result(timeout=5)
        assert all(button.enabled for button in buttons)
        assert "Valmis vastaus" in _labels(page)
