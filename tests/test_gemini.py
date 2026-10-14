"""Yhteisen Gemini-clientin testit ilman oikeita API-kutsuja."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from google.genai import errors, types

from app.core import config
from app.services.gemini import GeminiError, generate_gemini_text


@pytest.fixture(autouse=True)
def sdk(monkeypatch):
    """Kaikki tämän moduulin testit korvaavat SDK-clientin, myös virhetilanteissa."""
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-only-key")
    monkeypatch.setattr(config, "GEMINI_MODEL", "test-only-model")
    factory = MagicMock()
    client = factory.return_value.__enter__.return_value
    client.models.generate_content.return_value = SimpleNamespace(text="Faktat: koulutushaku. Ehdotus: pilotti. Tarkista hakukelpoisuus.")
    monkeypatch.setattr("app.services.gemini.genai.Client", factory)
    return factory, client


def test_instructions_contents_and_model_are_sent_and_client_is_closed(sdk):
    factory, client = sdk
    assert "Faktat:" in generate_gemini_text("Arvioi soveltuvuus.", "Haun tiedot")
    factory.assert_called_once()
    assert factory.call_args.kwargs["api_key"] == "test-only-key"
    assert factory.call_args.kwargs["vertexai"] is False
    options = factory.call_args.kwargs["http_options"]
    assert options.timeout == 60_000
    assert options.retry_options.attempts == 1
    sent = client.models.generate_content.call_args.kwargs
    assert sent["model"] == "test-only-model"
    assert sent["config"].system_instruction == "Arvioi soveltuvuus."
    assert sent["contents"] == "Haun tiedot"
    assert sent["config"].tools is None
    factory.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize("key,model,missing", [
    ("", "test-only-model", "GEMINI_API_KEY"),
    ("test-only-key", "", "GEMINI_MODEL"),
    ("", "", "GEMINI_API_KEY ja GEMINI_MODEL"),
])
def test_missing_configuration_is_clear_and_does_not_create_client(sdk, monkeypatch, key, model, missing):
    monkeypatch.setattr(config, "GEMINI_API_KEY", key)
    monkeypatch.setattr(config, "GEMINI_MODEL", model)
    with pytest.raises(GeminiError, match=missing):
        generate_gemini_text("Ohje", "Aineisto")
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
def test_errors_are_safe_finnish_messages_and_client_is_closed(sdk, caplog, error, message):
    factory, client = sdk
    client.models.generate_content.side_effect = error
    with pytest.raises(GeminiError, match=message) as caught:
        generate_gemini_text("Ohje", "Aineisto")
    assert "sensitive details" not in str(caught.value) + caplog.text
    assert "test-only-key" not in str(caught.value) + caplog.text
    factory.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize("response", [SimpleNamespace(text="  "), types.GenerateContentResponse()])
def test_empty_or_blocked_response_is_handled(sdk, response):
    sdk[1].models.generate_content.return_value = response
    with pytest.raises(GeminiError, match="ei palauttanut tekstivastausta"):
        generate_gemini_text("Ohje", "Aineisto")


def test_client_creation_failure_is_handled(sdk):
    sdk[0].side_effect = httpx.ConnectError("sensitive details")
    with pytest.raises(GeminiError, match="verkkoyhteyttä"):
        generate_gemini_text("Ohje", "Aineisto")
