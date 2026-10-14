"""Gemini-yhteenvedon ja hakemustekstin testit ilman verkkokutsuja."""

import json
from dataclasses import asdict
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from google.genai import errors, types
from nicegui import ui

from app.core import config
from app.models import EvaluationStatus
from app.services.ai_summary import SummaryError, generate_ai_summary
from app.services.application_text import ApplicationTextError, format_application_text
from app.services.funding_calls import get_funding_call
from tests.test_ai_summary import _selected_call
from tests.test_application_text import edit
from tests.test_funding_calls import _test_client
from tests.test_relevance_ui import _click, _page_client


@pytest.fixture(autouse=True)
def sdk(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(config, "GEMINI_MODEL", "test-model")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("app.services.ai_summary.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("app.services.application_text.PROJECT_ROOT", tmp_path)
    for name, text in [("organisaatioprofiili.md", "Organisaation koko profiili\nLoppu"),
                       ("ai-summary-prompt.md", "Yhteenveto-ohje\nLoppu"),
                       ("hakemusteksti-prompt.md", "Muotoiluohje\nLoppu")]:
        (tmp_path / name).write_text(text, encoding="utf-8")
    factory = MagicMock()
    generate = factory.return_value.__enter__.return_value.models.generate_content
    generate.return_value = SimpleNamespace(text="Tallennettu Gemini-arvio", candidates=None)
    monkeypatch.setattr("app.services.gemini.genai.Client", factory)
    # Gemini-virhe ei saa johtaa huomaamattomaan OpenAI-pyyntöön.
    monkeypatch.setattr(httpx.Client, "post", lambda *args, **kwargs: pytest.fail("Unexpected HTTP POST"))
    return factory, generate


def test_summary_sends_documents_and_context_without_openai_key(db_session, sdk):
    call = _selected_call(db_session)
    call.evaluation.status = EvaluationStatus.REJECTED
    call.evaluation.rejected_at = datetime(2026, 10, 8, 12, 0)
    db_session.commit()
    before = asdict(get_funding_call(db_session, call.id))
    assert generate_ai_summary(db_session, call.id) == "Tallennettu Gemini-arvio"
    sent = sdk[1].call_args.kwargs
    assert sent["model"] == "test-model"
    assert "Organisaation koko profiili\nLoppu" in sent["config"].system_instruction
    assert "Yhteenveto-ohje\nLoppu" in sent["config"].system_instruction
    assert "Muotoiluohje" not in sent["config"].system_instruction
    data = json.loads(sent["contents"])
    assert data["funding_call"]["title"] == call.title
    assert data["funding_call"]["description"] == call.description
    assert data["assessment_timezone"] == "Europe/Helsinki"
    assert data["source_page_read"] is False
    assert "raw_data" not in data["funding_call"]
    assert sent["config"].response_mime_type is None
    after = asdict(get_funding_call(db_session, call.id))
    assert after == before | {"ai_summary": "Tallennettu Gemini-arvio"}


def test_formatting_uses_json_schema_and_preserves_database(db_session, sdk):
    call = _selected_call(db_session)
    before = get_funding_call(db_session, call.id)
    sdk[1].return_value.text = json.dumps({"text": "Ääkköset.\nToinen rivi.", "additional_information": "Tarkista kohderyhmä."})
    result = format_application_text(before, "Tavoitteet?", "Oma luonnos", "Kriteeri", 5)
    sent = sdk[1].call_args.kwargs
    data = json.loads(sent["contents"])
    assert data["question"] == "Tavoitteet?"
    assert data["draft"] == "Oma luonnos"
    assert data["criteria"] == "Kriteeri"
    assert data["character_limit"] == 5
    assert data["funding_call"]["title"] == call.title
    assert "Organisaation koko profiili\nLoppu" in sent["config"].system_instruction
    assert "Muotoiluohje\nLoppu" in sent["config"].system_instruction
    assert "Oma luonnos" not in sent["config"].system_instruction
    assert sent["config"].response_mime_type == "application/json"
    assert set(sent["config"].response_json_schema["required"]) == {"text", "additional_information"}
    assert result.character_count == len("Ääkköset.\nToinen rivi.")
    assert result.excess == result.character_count - 5
    assert result.additional_information == "Tarkista kohderyhmä."
    assert get_funding_call(db_session, call.id) == before


@pytest.mark.parametrize("operation", ["summary", "formatting"])
@pytest.mark.parametrize("missing", ["GEMINI_API_KEY", "GEMINI_MODEL"])
def test_missing_configuration_does_not_send_request(db_session, sdk, monkeypatch, operation, missing):
    call = _selected_call(db_session)
    monkeypatch.setattr(config, missing, "")
    with pytest.raises((SummaryError, ApplicationTextError), match=missing):
        if operation == "summary":
            generate_ai_summary(db_session, call.id)
        else:
            format_application_text(get_funding_call(db_session, call.id), "Kysymys", "Luonnos")
    sdk[0].assert_not_called()


@pytest.mark.parametrize("operation", ["summary", "formatting"])
@pytest.mark.parametrize("error,message", [
    (httpx.ConnectError("private error"), "verkkoyhteyttä"),
    (httpx.ReadTimeout("private error"), "aikakatkaistiin"),
    (errors.ClientError(429, {"error": {"message": "private error"}}), "käyttöraja"),
    (errors.ServerError(503, {"error": {"message": "private error"}}), "API-virhe"),
])
def test_provider_errors_preserve_previous_summary(db_session, sdk, monkeypatch, operation, error, message):
    call = _selected_call(db_session)
    call.evaluation.ai_summary = "Vanha yhteenveto"
    db_session.commit()
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-be-used")
    sdk[1].side_effect = error
    with pytest.raises((SummaryError, ApplicationTextError), match=message) as caught:
        if operation == "summary":
            generate_ai_summary(db_session, call.id)
        else:
            format_application_text(get_funding_call(db_session, call.id), "Kysymys", "Luonnos")
    assert "private error" not in str(caught.value)
    db_session.refresh(call.evaluation)
    assert call.evaluation.ai_summary == "Vanha yhteenveto"


@pytest.mark.parametrize("text", ["", " ", "not-json", '{"text": 1}', '{"text":"", "additional_information":""}'])
def test_empty_and_invalid_formatting_answers_are_handled(db_session, sdk, text):
    call = _selected_call(db_session)
    sdk[1].return_value.text = text
    with pytest.raises(ApplicationTextError):
        format_application_text(get_funding_call(db_session, call.id), "Kysymys", "Luonnos")


@pytest.mark.parametrize("reason", [types.FinishReason.MAX_TOKENS, types.FinishReason.SAFETY])
def test_partial_or_blocked_summary_does_not_replace_previous(db_session, sdk, reason):
    call = _selected_call(db_session)
    call.evaluation.ai_summary = "Vanha yhteenveto"
    db_session.commit()
    sdk[1].return_value.candidates = [SimpleNamespace(finish_reason=reason)]
    with pytest.raises(SummaryError, match="ei saanut vastausta valmiiksi"):
        generate_ai_summary(db_session, call.id)
    db_session.refresh(call.evaluation)
    assert call.evaluation.ai_summary == "Vanha yhteenveto"


def test_ui_both_actions_work_with_gemini_and_no_openai_key(db_session, monkeypatch, sdk):
    call = _selected_call(db_session)
    with _test_client(db_session, monkeypatch) as client:
        page = _page_client(client.get("/hankkeet"))
        sdk[0].assert_not_called()
        client.portal.call(_click, page, "Muodosta AI-soveltuvuusarvio")
        assert "Tallennettu Gemini-arvio" in [e.text for e in page.elements.values() if isinstance(e, ui.label)]
        sdk[1].return_value.text = json.dumps({"text": "Valmis hakemusteksti.", "additional_information": ""})
        client.portal.call(_click, page, "Muotoile hakemustekstiä")
        client.portal.call(edit, page, "Hakemuksen osion kysymys tai otsikko", "Tavoitteet")
        client.portal.call(edit, page, "Oma hakemustekstiluonnos", "Luonnos")
        client.portal.call(_click, page, "Muotoile teksti")
        result = next(e for e in page.elements.values() if isinstance(e, ui.textarea) and e.props.get("label") == "Valmis hakemusteksti")
        assert result.value == "Valmis hakemusteksti."
        sdk[1].side_effect = httpx.ConnectError("private error")
        client.portal.call(_click, page, "Muotoile teksti")
        assert result.value == "Valmis hakemusteksti."
        assert next(e for e in page.elements.values() if isinstance(e, ui.button) and e.text == "Muotoile teksti").enabled
        assert client.get(f"/api/funding-calls/{call.id}").json()["ai_summary"] == "Tallennettu Gemini-arvio"


@pytest.mark.parametrize("operation", ["summary", "formatting"])
def test_unknown_provider_does_not_send_request(db_session, monkeypatch, sdk, operation):
    call = _selected_call(db_session)
    monkeypatch.setattr(config, "AI_PROVIDER", "typo")
    with pytest.raises((SummaryError, ApplicationTextError), match="AI_PROVIDER"):
        if operation == "summary":
            generate_ai_summary(db_session, call.id)
        else:
            format_application_text(get_funding_call(db_session, call.id), "K", "T")
    sdk[0].assert_not_called()
