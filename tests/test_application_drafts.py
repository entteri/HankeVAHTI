from copy import deepcopy
from dataclasses import replace
import json

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import EuraApplicationDraft, FundingCall
from app.services.eura_application_drafts import (
    EuraApplicationDraftError, generate_application_field, get_application_draft, save_application_draft,
)
from app.services.application_text import ApplicationTextError
from app.services.funding_calls import get_funding_call
from app.services.settings import delete_all_funding_calls
from tests.test_ai_summary import _selected_call
from tests.test_application_text import response


@pytest.fixture
def call(db_session):
    model = _selected_call(db_session)
    return get_funding_call(db_session, model.id)


@pytest.fixture
def content():
    return {"project_context": "Opettajien digiosaamisen kehittäminen työpajoissa.",
            "fields": {"project_name": "Digipaja", "need": "Opettajat tarvitsevat tukea.",
                       "objectives": "Oma tavoitteeni", "public_summary": "Suomenkielinen tiivistelmä"},
            "confirmed_fields": ["project_name", "need"]}


def test_create_update_reload_and_other_data_unchanged(db_session, call, content):
    before = get_funding_call(db_session, call.id)
    assert get_application_draft(db_session, call.id) is None
    draft = save_application_draft(db_session, call.id, content)
    original_id, created_at = draft.id, draft.created_at
    content["fields"]["need"] = "Muokattu tarve"
    assert draft.content_json["fields"]["need"] != content["fields"]["need"]
    save_application_draft(db_session, call.id, content)
    db_session.expire_all()
    saved = get_application_draft(db_session, call.id)
    assert saved.id == original_id and saved.created_at == created_at
    assert saved.updated_at >= saved.created_at
    assert saved.content_json["fields"]["need"] == "Muokattu tarve"
    assert saved.content_json["project_context"] == content["project_context"]
    assert db_session.scalar(select(func.count()).select_from(EuraApplicationDraft)) == 1
    assert get_funding_call(db_session, call.id) == before


def test_unique_constraint(db_session, call, content):
    save_application_draft(db_session, call.id, content)
    db_session.add(EuraApplicationDraft(funding_call_id=call.id, content_json={}))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_missing_call_and_foreign_key(db_session, content):
    with pytest.raises(EuraApplicationDraftError, match="ei löydy"):
        save_application_draft(db_session, 9999, content)
    db_session.add(EuraApplicationDraft(funding_call_id=9999, content_json={}))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize("bulk", [False, True])
def test_call_deletion_cascades(db_session, call, content, bulk):
    save_application_draft(db_session, call.id, content)
    if bulk:
        delete_all_funding_calls(db_session)
    else:
        db_session.delete(db_session.get(FundingCall, call.id))
        db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(EuraApplicationDraft)) == 0


def test_invalid_update_preserves_saved_content(db_session, call, content):
    original = deepcopy(save_application_draft(db_session, call.id, content).content_json)
    content["fields"]["budget"] = "123456"
    with pytest.raises(EuraApplicationDraftError):
        save_application_draft(db_session, call.id, content)
    assert get_application_draft(db_session, call.id).content_json == original


@pytest.fixture
def ai(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-test-key")
    monkeypatch.setattr("app.services.eura_application_drafts.PROJECT_ROOT", tmp_path)
    (tmp_path / "organisaatioprofiili.md").write_text("Testiorganisaation profiili", encoding="utf-8")
    (tmp_path / "hankehakemus-prompt.md").write_text("Kentän järjestelmäohje", encoding="utf-8")
    (tmp_path / "hakemusteksti-prompt.md").write_text("Yhteiset kirjoitussäännöt\nKoko ohje", encoding="utf-8")
    (tmp_path / "arviointikriteerit.md").write_text("Organisaation täydentävä taustakuvaus\nKoko tausta", encoding="utf-8")


@pytest.mark.parametrize("provider", ["gemini", "openai"])
def test_ai_context_allowlist_and_provider_reuse(call, content, ai, monkeypatch, provider):
    monkeypatch.setattr("app.core.config.AI_PROVIDER", provider)
    call = replace(call, ai_summary="Tallennettu soveltuvuusarvio: tarkista hakukelpoisuus.")
    content["contact_person"] = "SALAINEN-YHTEYSTIETO"
    content["raw_data"] = {"secret": "SALAINEN-RAW"}
    content["fields"]["contact_email"] = "SALAINEN-EMAIL"
    content["confirmed_fields"].append("contact_email")
    content["additional_information"] = {"need": "EI-KONTEKSTIIN"}
    before = deepcopy(content)
    seen = []
    def inspect(instructions, data):
        seen.append(data)
        assert "Testiorganisaation profiili" in instructions
        assert "Kentän järjestelmäohje" in instructions
        assert "Yhteiset kirjoitussäännöt\nKoko ohje" in instructions
        assert "Palauta vain JSON-objekti" in instructions
        assert "Organisaation täydentävä taustakuvaus" not in instructions
        assert data["organisation_assessment_background"] == {
            "source_file": "arviointikriteerit.md", "content": "Organisaation täydentävä taustakuvaus\nKoko tausta",
        }
        assert data["assessments_not_project_facts"]["ai_summary"] == call.ai_summary
        assert content["project_context"] not in instructions
        assert data["question"] == "Mitkä ovat hankkeen tavoitteet?"
        assert data["project_context"] == content["project_context"]
        assert data["draft"] == "Oma tavoitteeni"
        assert data["operation"] == "refine"
        assert data["source_page_read"] is False
        assert data["funding_call"]["title"] == call.title
        assert data["funding_call"]["call_identifier"] == (call.call_identifier or call.source_id)
        assert data["confirmed_project_texts"] == {"project_name": "Digipaja", "need": "Opettajat tarvitsevat tukea."}
        assert not any(secret in json.dumps(data) for secret in ("SALAINEN", "EI-KONTEKSTIIN", "Suomenkielinen tiivistelmä"))
    def gemini(instructions, message, **kwargs):
        inspect(instructions, json.loads(message))
        assert kwargs["json_schema"]["required"] == ["text", "additional_information"]
        return json.dumps({"text": "Ehdotus", "additional_information": "Tarkista tämä"})
    def openai(request):
        payload = json.loads(request.content)
        inspect(payload["instructions"], json.loads(payload["input"]))
        assert payload["store"] is False
        assert payload["text"]["format"]["type"] == "json_schema"
        return response("Ehdotus", "Tarkista tämä")
    monkeypatch.setattr("app.services.application_text.generate_gemini_text", gemini)
    with httpx.Client(transport=httpx.MockTransport(openai)) as client:
        result = generate_application_field(call, "objectives", content, client=client)
    assert len(seen) == 1
    assert result.text == "Ehdotus" and result.additional_information == "Tarkista tämä"
    assert content == before


@pytest.mark.parametrize("filename", ["hakemusteksti-prompt.md", "arviointikriteerit.md"])
@pytest.mark.parametrize("invalid", ["missing", "empty"])
def test_shared_guidance_error_prevents_ai_request(call, content, ai, monkeypatch, tmp_path, filename, invalid):
    path = tmp_path / filename
    if invalid == "missing":
        path.unlink()
    else:
        path.write_text("  ", encoding="utf-8")
    monkeypatch.setattr("app.services.eura_application_drafts.request_application_text", lambda *a, **k: pytest.fail("Unexpected request"))
    before = deepcopy(content)
    with pytest.raises(ApplicationTextError, match=filename):
        generate_application_field(call, "objectives", content)
    assert content == before


def test_shared_guidance_is_reread_for_each_request(call, content, ai, monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr("app.services.eura_application_drafts.request_application_text", lambda instructions, data, **kwargs: seen.append((instructions, data)))
    generate_application_field(call, "objectives", content)
    (tmp_path / "hakemusteksti-prompt.md").write_text("Uusi yhteinen kirjoitusohje", encoding="utf-8")
    (tmp_path / "arviointikriteerit.md").write_text("Uusi organisaatiotausta", encoding="utf-8")
    generate_application_field(call, "objectives", content)
    assert "Uusi yhteinen kirjoitusohje" not in seen[0][0]
    assert "Uusi yhteinen kirjoitusohje" in seen[1][0]
    assert seen[1][1]["organisation_assessment_background"]["content"] == "Uusi organisaatiotausta"


@pytest.mark.parametrize("field_id, change, message", [
    ("english_name", "unconfirmed", "suomenkielinen"),
    ("english_summary", "none", "suomenkielinen"),
    ("related_projects", "none", "muista hankkeista"),
    ("project_name", "none", "ei voi"),
    ("budget", "none", "ei voi"),
    ("risk_1_mitigation", "none", "riski"),
])
def test_ai_preconditions_no_request(call, content, monkeypatch, field_id, change, message):
    monkeypatch.setattr("app.services.eura_application_drafts.request_application_text", lambda *a, **k: pytest.fail("Unexpected request"))
    content["project_context"] = ""  # Optional ideas do not bypass field-specific safeguards.
    if change == "unconfirmed":
        content["confirmed_fields"] = []
    with pytest.raises(ApplicationTextError, match=message):
        generate_application_field(call, field_id, content)


@pytest.mark.parametrize("provider", ["gemini", "openai"])
@pytest.mark.parametrize("ideas", [None, "", "  \n "])
@pytest.mark.parametrize("field_id", ["objectives", "public_summary"])
def test_empty_ideas_use_funding_description_without_inventing_input(call, ai, monkeypatch, provider, ideas, field_id):
    monkeypatch.setattr("app.core.config.AI_PROVIDER", provider)
    content = {"fields": {}, "confirmed_fields": []}
    if ideas is not None:
        content["project_context"] = ideas
    before = deepcopy(content)
    seen = []
    def inspect(data):
        seen.append(data)
        assert data["project_context"] == ""
        assert data["funding_call"]["description"] == call.description
        assert data["confirmed_project_texts"] == {}
        assert data["field_id"] == field_id
        assert data["operation"] == "suggest"
    def gemini(instructions, message, **kwargs):
        inspect(json.loads(message))
        return json.dumps({"text": "Hankkeessa voitaisiin kehittää digitaitoja.", "additional_information": "Vahvista tavoite."})
    def openai(request):
        inspect(json.loads(json.loads(request.content)["input"]))
        return response("Hankkeessa voitaisiin kehittää digitaitoja.", "Vahvista tavoite.")
    monkeypatch.setattr("app.services.application_text.generate_gemini_text", gemini)
    with httpx.Client(transport=httpx.MockTransport(openai)) as client:
        result = generate_application_field(call, field_id, content, client=client)
    assert len(seen) == 1
    assert result.text.startswith("Hankkeessa voitaisiin")
    assert result.additional_information == "Vahvista tavoite."
    assert content == before


@pytest.mark.parametrize("field_id,basis", [("english_name", "project_name"), ("english_summary", "public_summary")])
def test_english_uses_confirmed_finnish(call, content, ai, monkeypatch, field_id, basis):
    content["confirmed_fields"].append(basis)
    def request(instructions, data, **kwargs):
        assert data["language"] == "en"
        assert data["operation"] == "translate"
        assert data["translation_source"] == content["fields"][basis]
    monkeypatch.setattr("app.services.eura_application_drafts.request_application_text", request)
    generate_application_field(call, field_id, content)


@pytest.mark.parametrize("kind", ["missing_key", "api", "empty", "additional_only", "timeout"])
def test_errors_and_missing_information_do_not_mutate_draft(call, content, ai, monkeypatch, kind):
    monkeypatch.setattr("app.core.config.AI_PROVIDER", "openai")
    before = deepcopy(content)
    if kind == "missing_key":
        monkeypatch.delenv("OPENAI_API_KEY")
    def handler(request):
        if kind == "timeout":
            raise httpx.ReadTimeout("timeout")
        return httpx.Response(503) if kind == "api" else response("", "Mikä tavoite?" if kind == "additional_only" else "")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        if kind == "additional_only":
            result = generate_application_field(call, "objectives", content, client=client)
            assert result.text == "" and result.additional_information == "Mikä tavoite?"
        else:
            with pytest.raises(ApplicationTextError):
                generate_application_field(call, "objectives", content, client=client)
    assert content == before


def test_gemini_error_is_translated_without_openai_fallback(call, content, ai, monkeypatch):
    from app.services.gemini import GeminiError
    monkeypatch.setattr("app.core.config.AI_PROVIDER", "gemini")
    def fail(*args, **kwargs):
        raise GeminiError("Geminin testivirhe")
    monkeypatch.setattr("app.services.application_text.generate_gemini_text", fail)
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **k: pytest.fail("No fallback allowed"))
    before = deepcopy(content)
    with pytest.raises(ApplicationTextError, match="Geminin testivirhe"):
        generate_application_field(call, "objectives", content)
    assert content == before
