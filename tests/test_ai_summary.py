import asyncio
import json
from threading import Event

import httpx
import pytest
from nicegui import events, ui
from sqlalchemy import select

from app.models import Evaluation, EvaluationStatus, FundingCall
from app.services.ai_summary import OPENAI_RESPONSES_URL, SummaryError, generate_ai_summary
from tests.test_funding_calls import _test_client
from tests.test_relevance_ui import _click, _page_client


@pytest.fixture(autouse=True)
def openai_provider(monkeypatch):
    """Säilytä alkuperäisen OpenAI-vaihtoehdon regressiotestit."""
    monkeypatch.setattr("app.core.config.AI_PROVIDER", "openai")


def _selected_call(session):
    call = FundingCall(
        source="EURA",
        source_id="test-1",
        title="Digitaalisen oppimisen hanke",
        description="Hanke kehittää henkilöstön digitaitoja.",
        fund="ESR+",
        evaluation=Evaluation(status=EvaluationStatus.PARTICIPATE, suitability_score=80, suitability_summary="Oma arvio"),
    )
    session.add(call)
    session.commit()
    return call


def test_ai_summary_uses_current_files_and_preserves_manual_evaluation(db_session, tmp_path, monkeypatch):
    call = _selected_call(db_session)
    profile = tmp_path / "organisaatioprofiili.md"
    criteria = tmp_path / "ai-summary-prompt.md"
    profile.write_text("Asiakas kouluttaa henkilöstöä digitaidoissa.", encoding="utf-8")
    criteria.write_text("Vertaa asiakkaan osaamista hankkeen tavoitteisiin.", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setattr("app.services.ai_summary.PROJECT_ROOT", tmp_path)

    def handler(request):
        assert str(request.url) == OPENAI_RESPONSES_URL
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert payload["store"] is False
        assert "Asiakas kouluttaa henkilöstöä digitaidoissa." in payload["instructions"]
        assert "Vertaa asiakkaan osaamista hankkeen tavoitteisiin." in payload["instructions"]
        assert "Hanke kehittää henkilöstön digitaitoja." in payload["input"]
        return httpx.Response(200, json={
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "Hanke sopii digitaitoihin. Rahoituskelpoisuus on selvitettävä."}]}],
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        summary = generate_ai_summary(db_session, call.id, client=client)

    db_session.expire_all()
    saved = db_session.scalar(select(FundingCall).where(FundingCall.id == call.id))
    assert summary == saved.evaluation.ai_summary
    assert saved.evaluation.suitability_summary == "Oma arvio"
    assert saved.evaluation.suitability_score == 80
    assert saved.evaluation.status is EvaluationStatus.PARTICIPATE


def test_ai_summary_requires_profile_and_selected_call(db_session, tmp_path, monkeypatch):
    call = _selected_call(db_session)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with pytest.raises(SummaryError, match="organisaatioprofiili.md puuttuu"):
        generate_ai_summary(db_session, call.id, profile_path=tmp_path / "organisaatioprofiili.md")

    with pytest.raises(SummaryError, match="ei löydy"):
        generate_ai_summary(db_session, call.id + 100)


def test_ai_summary_failure_keeps_previous_summary(db_session, tmp_path, monkeypatch):
    call = _selected_call(db_session)
    call.evaluation.ai_summary = "Aiempi yhteenveto"
    db_session.commit()
    profile = tmp_path / "organisaatioprofiili.md"
    criteria = tmp_path / "ai-summary-prompt.md"
    profile.write_text("Asiakas", encoding="utf-8")
    criteria.write_text("Kriteerit", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client:
        with pytest.raises(SummaryError, match="Tekoälypalveluun"):
            generate_ai_summary(db_session, call.id, client=client, profile_path=profile, prompt_path=criteria)

    db_session.refresh(call.evaluation)
    assert call.evaluation.ai_summary == "Aiempi yhteenveto"


@pytest.fixture
def context_files(tmp_path, monkeypatch):
    (tmp_path / "organisaatioprofiili.md").write_text("Asiakas", encoding="utf-8")
    (tmp_path / "ai-summary-prompt.md").write_text("Kriteerit", encoding="utf-8")
    monkeypatch.setattr("app.services.ai_summary.PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


def test_missing_api_key_does_not_send_request(db_session, monkeypatch, context_files):
    call = _selected_call(db_session)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def unexpected_request(request):
        pytest.fail("Missing API key must not trigger a request")

    with httpx.Client(transport=httpx.MockTransport(unexpected_request)) as client:
        with pytest.raises(SummaryError, match="OPENAI_API_KEY puuttuu"):
            generate_ai_summary(db_session, call.id, client=client)
    assert call.evaluation.ai_summary is None


@pytest.mark.parametrize("payload", [
    {"status": "completed", "output": []},
    {"status": "incomplete", "output": []},
])
def test_unusable_response_preserves_existing_summary(db_session, context_files, payload):
    call = _selected_call(db_session)
    call.evaluation.ai_summary = "Aiempi yhteenveto"
    db_session.commit()
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
        with pytest.raises(SummaryError):
            generate_ai_summary(db_session, call.id, client=client)
    db_session.refresh(call.evaluation)
    assert call.evaluation.ai_summary == "Aiempi yhteenveto"


def test_summary_button_saves_and_displays_summary_alongside_relevance_and_gemini(db_session, monkeypatch, context_files):
    call = _selected_call(db_session)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "Tallennettu AI-yhteenveto"}]}],
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as api_client:
        monkeypatch.setattr(
            "app.ui.funding_calls.generate_ai_summary",
            lambda session, call_id: generate_ai_summary(session, call_id, client=api_client),
        )
        with _test_client(db_session, monkeypatch) as client:
            page = _page_client(client.get("/osallistuttavat"))
            assert not requests
            client.portal.call(_click, page, "AI-soveltuvuusarvio")
            assert len(requests) == 1
            client.portal.call(_click, page, "Lisätiedot")
            labels = [e.text for e in page.elements.values() if isinstance(e, ui.label)]
            assert labels.count("Tallennettu AI-yhteenveto") == 2
            assert "Oma arvio" in labels
            assert "Relevanssi: 80 / 100" in labels
            assert not any(isinstance(e, ui.button) and e.text == "AI-sparraaja" for e in page.elements.values())
            assert client.get(f"/api/funding-calls/{call.id}").json()["ai_summary"] == "Tallennettu AI-yhteenveto"
            client.portal.call(_click, page, "Arvioimatta")
            client.portal.call(_click, page, "Vahvista")
            saved = client.get(f"/api/funding-calls/{call.id}").json()
            assert saved["status"] == "NEW"
            assert saved["ai_summary"] == "Tallennettu AI-yhteenveto"
            assert saved["suitability_score"] == 80


def test_summary_button_prevents_duplicate_requests_and_recovers_after_failure(db_session, monkeypatch):
    _selected_call(db_session)
    started, release = Event(), Event()
    calls = []

    def slow_failure(session, call_id):
        calls.append(call_id)
        started.set()
        assert release.wait(timeout=4)
        raise SummaryError("Testivirhe")

    monkeypatch.setattr("app.ui.funding_calls.generate_ai_summary", slow_failure)
    with _test_client(db_session, monkeypatch) as client:
        page = _page_client(client.get("/osallistuttavat"))
        button = next(e for e in page.elements.values() if isinstance(e, ui.button) and e.text == "AI-soveltuvuusarvio")
        pending = client.portal.start_task_soon(_click, page, "AI-soveltuvuusarvio")
        try:
            assert started.wait(timeout=2)
            assert not button.enabled
            assert client.get("/health").status_code == 200

            async def repeat_event():
                with page:
                    listener = next(e for e in button._event_listeners.values() if e.type == "click")
                    before = asyncio.all_tasks()
                    events.handle_event(listener.handler, events.GenericEventArguments(sender=button, client=page, args=None))
                    tasks = asyncio.all_tasks() - before
                    if tasks:
                        await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)

            client.portal.call(repeat_event)
            assert len(calls) == 1
        finally:
            release.set()
            pending.result(timeout=5)
        new_button = next(e for e in page.elements.values() if isinstance(e, ui.button) and e.text == "AI-soveltuvuusarvio")
        assert new_button.enabled
        client.portal.call(_click, page, "AI-soveltuvuusarvio")
        assert len(calls) == 2


@pytest.mark.parametrize("filename", ["organisaatioprofiili.md", "ai-summary-prompt.md"])
@pytest.mark.parametrize("content", [None, "  \n\t"])
def test_missing_or_empty_document_preserves_summary(db_session, tmp_path, monkeypatch, context_files, filename, content):
    call = _selected_call(db_session)
    call.evaluation.ai_summary = "Vanha arvio"
    db_session.commit()
    path = tmp_path / filename
    if content is None:
        path.unlink()
    else:
        path.write_text(content, encoding="utf-8")
    def unexpected(request):
        pytest.fail("Invalid documents must not send an AI request")
    with httpx.Client(transport=httpx.MockTransport(unexpected)) as client:
        with pytest.raises(SummaryError, match=filename):
            generate_ai_summary(db_session, call.id, client=client)
    db_session.refresh(call.evaluation)
    assert call.evaluation.ai_summary == "Vanha arvio"


def test_new_call_details_generate_long_summary_without_changing_decision(db_session, monkeypatch, context_files):
    from datetime import date, datetime
    from zoneinfo import ZoneInfo
    from app.models import Participation
    call = _selected_call(db_session)
    call.evaluation.status = EvaluationStatus.NEW
    call.application_start_date = date(2026, 10, 1)
    call.application_end_date = date(2026, 11, 1)
    db_session.commit()
    long_summary = "### Kokonaisarvio\nVaatii lisäselvitystä.\n" + "Perustelu. " * 1000
    requests = []
    def handler(request):
        payload = json.loads(request.content)
        data = json.loads(payload["input"])
        requests.append(data)
        assert "Asiakas" in payload["instructions"]
        assert "Kriteerit" in payload["instructions"]
        assert "Asiakas" not in payload["input"]
        assert data["funding_call"]["title"] == call.title
        assert data["funding_call"]["description"] == call.description
        assert data["funding_call"]["source"] == "EURA"
        assert data["funding_call"]["fund"] == "ESR+"
        assert data["funding_call"]["application_start_date"] == "2026-10-01"
        assert data["funding_call"]["application_end_date"] == "2026-11-01"
        assert data["funding_call"]["source_url"].startswith("https://")
        assert data["assessment_date"] == datetime.now(ZoneInfo("Europe/Helsinki")).date().isoformat()
        assert data["source_page_read"] is False
        assert payload["max_output_tokens"] > 350
        return httpx.Response(200, json={"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": long_summary}]}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as api_client:
        monkeypatch.setattr("app.ui.funding_calls.generate_ai_summary", lambda session, call_id: generate_ai_summary(session, call_id, client=api_client))
        with _test_client(db_session, monkeypatch) as client:
            page = _page_client(client.get("/arvioi"))
            assert not requests
            client.portal.call(_click, page, "Lisätiedot")
            client.portal.call(_click, page, "Muodosta AI-soveltuvuusarvio")
            assert len(requests) == 1
            assert long_summary.strip() in [e.text for e in page.elements.values() if isinstance(e, ui.label)]
            saved = client.get(f"/api/funding-calls/{call.id}").json()
            assert saved["status"] == "NEW"
            assert saved["suitability_score"] == 80
            assert saved["ai_summary"] == long_summary.strip()
    db_session.refresh(call.evaluation)
    assert call.evaluation.suitability_summary == "Oma arvio"
    assert db_session.scalar(select(Participation)) is None


def test_missing_source_fields_and_malformed_response(db_session, context_files):
    call = _selected_call(db_session)
    call.source = "OTHER"
    call.source_url = None
    call.description = None
    call.evaluation.ai_summary = "Vanha arvio"
    db_session.commit()
    def handler(request):
        data = json.loads(json.loads(request.content)["input"])["funding_call"]
        assert data["description"] is None
        assert data["source_url"] is None
        assert data["application_end_date"] is None
        return httpx.Response(200, text="invalid JSON")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SummaryError, match="virheellisen vastauksen"):
            generate_ai_summary(db_session, call.id, client=client)
    db_session.refresh(call.evaluation)
    assert call.evaluation.ai_summary == "Vanha arvio"


def test_documents_read_again_and_independent_of_working_directory(tmp_path, monkeypatch):
    from app.services.ai_documents import read_ai_document
    from app.core.config import PROJECT_ROOT
    monkeypatch.chdir(tmp_path)
    assert read_ai_document("organisaatioprofiili.md") == (PROJECT_ROOT / "organisaatioprofiili.md").read_text(encoding="utf-8")
    document = tmp_path / "prompt.md"
    document.write_text("Ensimmäinen", encoding="utf-8")
    assert read_ai_document("prompt.md", root=tmp_path) == "Ensimmäinen"
    document.write_text("Toinen", encoding="utf-8")
    assert read_ai_document("prompt.md", root=tmp_path) == "Toinen"


@pytest.mark.parametrize("error", [httpx.ConnectError("offline"), httpx.ReadTimeout("timeout")])
def test_network_failure_preserves_previous_summary(db_session, context_files, error):
    call = _selected_call(db_session)
    call.evaluation.ai_summary = "Vanha arvio"
    db_session.commit()
    def handler(request):
        raise error
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SummaryError, match="Tekoälypalveluun"):
            generate_ai_summary(db_session, call.id, client=client)
    db_session.refresh(call.evaluation)
    assert call.evaluation.ai_summary == "Vanha arvio"
