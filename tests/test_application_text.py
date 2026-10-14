import json

import httpx
import pytest
from nicegui import ui

from app.services.application_text import ApplicationTextError, ApplicationTextResult, format_application_text
from app.services.funding_calls import list_funding_calls
from tests.test_ai_summary import _selected_call
from tests.test_funding_calls import _test_client
from tests.test_relevance_ui import _click, _page_client


@pytest.fixture(autouse=True)
def openai_provider(monkeypatch):
    """Säilytä alkuperäisen OpenAI-vaihtoehdon regressiotestit."""
    monkeypatch.setattr("app.core.config.AI_PROVIDER", "openai")


@pytest.fixture
def context(db_session, tmp_path, monkeypatch):
    call = _selected_call(db_session)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("app.services.application_text.PROJECT_ROOT", tmp_path)
    (tmp_path / "organisaatioprofiili.md").write_text("Koko profiili\nLoppu", encoding="utf-8")
    (tmp_path / "hakemusteksti-prompt.md").write_text("Koko muotoiluprompti\nLoppu", encoding="utf-8")
    return list_funding_calls(db_session)[0][0]


def response(text="Selkeä teksti.", additional=""):
    return httpx.Response(200, json={"status": "completed", "output": [{"type": "message", "content": [{
        "type": "output_text", "text": json.dumps({"text": text, "additional_information": additional})
    }]}]})


def test_inputs_documents_and_exact_count(context, db_session):
    before = (context.status, context.suitability_score, context.ai_summary)
    def handler(request):
        payload = json.loads(request.content)
        assert "Koko profiili\nLoppu" in payload["instructions"]
        assert "Koko muotoiluprompti\nLoppu" in payload["instructions"]
        data = json.loads(payload["input"])
        assert data["question"] == "Tavoitteet?"
        assert data["draft"] == "Oma luonnos"
        assert data["criteria"] == "Rahoittajan kriteerit"
        assert "Oma luonnos" not in payload["instructions"]
        assert data["funding_call"]["title"] == context.title
        assert data["source_page_read"] is False
        assert payload["store"] is False
        return response("Ääkköset, välit.\nToinen rivi.")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = format_application_text(context, "Tavoitteet?", "Oma luonnos", "Rahoittajan kriteerit", 10, client=client)
    assert result.character_count == len("Ääkköset, välit.\nToinen rivi.")
    assert result.excess == result.character_count - 10
    saved = list_funding_calls(db_session)[0][0]
    assert (saved.status, saved.suitability_score, saved.ai_summary) == before


@pytest.mark.parametrize("limit, excess", [(None, 0), (5, 0), (4, 1)])
def test_count_and_limit(limit, excess):
    result = ApplicationTextResult("A, B!", "Lisätieto", limit)
    assert result.character_count == 5
    assert result.excess == excess


@pytest.mark.parametrize("question,draft,limit", [("", "Teksti", None), ("Kysymys", " ", None), ("K", "T", 0), ("K", "T", 1.5)])
def test_invalid_input_does_not_request(context, question, draft, limit):
    with httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("Unexpected request"))) as client:
        with pytest.raises(ApplicationTextError):
            format_application_text(context, question, draft, character_limit=limit, client=client)


def test_missing_key(context, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    with httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("Unexpected request"))) as client:
        with pytest.raises(ApplicationTextError, match="OPENAI_API_KEY puuttuu"):
            format_application_text(context, "K", "T", client=client)


@pytest.mark.parametrize("filename", ["organisaatioprofiili.md", "hakemusteksti-prompt.md"])
@pytest.mark.parametrize("empty", [True, False])
def test_invalid_documents(context, tmp_path, filename, empty):
    path = tmp_path / filename
    if empty:
        path.write_text("  ", encoding="utf-8")
    else:
        path.unlink()
    with httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("Unexpected request"))) as client:
        with pytest.raises(ApplicationTextError, match=filename):
            format_application_text(context, "K", "T", client=client)


@pytest.mark.parametrize("kind", ["http", "timeout", "malformed", "incomplete", "empty"])
def test_api_failures(context, kind):
    def handler(request):
        if kind == "timeout":
            raise httpx.ReadTimeout("timeout")
        if kind == "http":
            return httpx.Response(503)
        if kind == "incomplete":
            return httpx.Response(200, json={"status": "incomplete"})
        if kind == "empty":
            return response("", "")
        return httpx.Response(200, text="invalid")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ApplicationTextError):
            format_application_text(context, "K", "T", client=client)


def test_missing_facts_return_questions(context):
    with httpx.Client(transport=httpx.MockTransport(lambda _: response("", "Mikä on kohderyhmä?"))) as client:
        result = format_application_text(context, "K", "T", client=client)
    assert result.text == ""
    assert result.character_count == 0
    assert result.additional_information == "Mikä on kohderyhmä?"


def edit(page, label, value):
    with page:
        field = next(e for e in page.elements.values() if isinstance(e, (ui.input, ui.textarea)) and e.props.get("label") == label)
        field.set_value(value)


def test_ui_result_excess_copy_and_failure(db_session, monkeypatch):
    _selected_call(db_session)
    calls, copied = [], []
    def formatter(call, question, draft, criteria, limit):
        calls.append((question, draft, criteria, limit))
        if len(calls) > 1:
            raise ApplicationTextError("Testivirhe")
        return ApplicationTextResult("Valmis teksti.", "Tarkista kohderyhmä.", limit)
    monkeypatch.setattr("app.ui.application_text.format_application_text", formatter)
    monkeypatch.setattr(ui.clipboard, "write", lambda text: copied.append(text))
    with _test_client(db_session, monkeypatch) as client:
        page = _page_client(client.get("/hankkeet"))
        client.portal.call(_click, page, "Muotoile hakemustekstiä")
        assert not calls
        for label, value in [("Hakemuksen osion kysymys tai otsikko", "Tavoitteet"), ("Oma hakemustekstiluonnos", "Luonnos"), ("Arviointikriteerit tai lisäohjeet (valinnainen)", "Kriteerit"), ("Merkkimääräraja (valinnainen)", "5")]:
            client.portal.call(edit, page, label, value)
        client.portal.call(_click, page, "Muotoile teksti")
        assert calls == [("Tavoitteet", "Luonnos", "Kriteerit", 5)]
        labels = [e.text for e in page.elements.values() if isinstance(e, ui.label)]
        assert "Merkkimäärä: 14 / 5" in labels
        assert "Merkkimääräraja ylittyy 9 merkillä. Tekstiä ei katkaistu." in labels
        result = next(e for e in page.elements.values() if isinstance(e, ui.textarea) and e.props.get("label") == "Valmis hakemusteksti")
        assert result.value == "Valmis teksti."
        client.portal.call(_click, page, "Kopioi valmis teksti")
        assert copied == ["Valmis teksti."]
        client.portal.call(_click, page, "Muotoile teksti")
        assert result.value == "Valmis teksti."
        assert "Testivirhe" in [e.text for e in page.elements.values() if isinstance(e, ui.label)]


def test_ui_without_key(db_session, monkeypatch):
    _selected_call(db_session)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with _test_client(db_session, monkeypatch) as client:
        page = _page_client(client.get("/hankkeet"))
        client.portal.call(_click, page, "Muotoile hakemustekstiä")
        client.portal.call(edit, page, "Hakemuksen osion kysymys tai otsikko", "Kysymys")
        client.portal.call(edit, page, "Oma hakemustekstiluonnos", "Luonnos")
        client.portal.call(_click, page, "Muotoile teksti")
        assert any("OPENAI_API_KEY puuttuu" in e.text for e in page.elements.values() if isinstance(e, ui.label))
        assert next(e for e in page.elements.values() if isinstance(e, ui.button) and e.text == "Muotoile teksti").enabled
