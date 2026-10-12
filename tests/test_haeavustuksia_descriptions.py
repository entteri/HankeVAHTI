from datetime import datetime

import pytest
from nicegui import ui
from sqlalchemy import select

from app.importers.haeavustuksia import _localized_text, import_haeavustuksia
from app.models import EvaluationStatus, FundingCall, Participation
from tests.test_funding_calls import _test_client
from tests.test_importers import _client, _fixture
from tests.test_relevance_ui import _page_client


def _document(text):
    return {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": text}]},
    ]}


@pytest.mark.parametrize("value,expected", [
    ({"fi": "", "sv": "", "en": "", "richFi": _document("Vesien tilan parantaminen.")}, "Vesien tilan parantaminen."),
    ({"fi": "  Tavallinen kuvaus  ", "richFi": _document("Muotoiltu kuvaus")}, "Tavallinen kuvaus"),
    ({"fi": "", "sv": "Svenska", "richFi": _document("Suomeksi")}, "Suomeksi"),
    ({"fi": "", "richFi": _document("  "), "richSv": _document("Svenska")}, "Svenska"),
    ({"richEn": _document("English")}, "English"),
    ({"richFi": {"type": "doc", "content": [{"type": "paragraph"}]}}, None),
    ({"richFi": {"type": "doc", "content": [None, 1, {"type": "text", "text": 3}]}}, None),
    ({"richFi": "invalid", "en": "Fallback"}, "Fallback"),
    (" Plain text ", "Plain text"),
    (None, None),
])
def test_localized_description_supports_rich_text_and_language_fallbacks(value, expected):
    assert _localized_text(value) == expected


def test_rich_description_preserves_blocks_inline_text_and_line_breaks():
    value = {"richFi": {"type": "doc", "content": [
        {"type": "heading", "content": [{"type": "text", "text": "Otsikko"}]},
        {"type": "paragraph", "content": [
            {"type": "text", "text": "Alku "},
            {"type": "text", "text": "lihavointi", "marks": [{"type": "bold"}]},
            {"type": "text", "text": "."},
            {"type": "hardBreak"},
            {"type": "text", "text": "Uusi rivi"},
        ]},
        {"type": "bulletList", "content": [
            {"type": "listItem", "content": _document("Ensimmäinen kohta")["content"]},
            {"type": "listItem", "content": _document("Toinen kohta")["content"]},
        ]},
        {"type": "image", "attrs": {"src": "https://example.invalid/image"}},
    ]}}
    assert _localized_text(value) == "Otsikko\nAlku lihavointi.\nUusi rivi\nEnsimmäinen kohta\nToinen kohta"


def test_import_repairs_existing_description_and_ui_escapes_rich_text(db_session, monkeypatch):
    page = _fixture("hae_page_1.json") | {"pageCount": 1}
    item = page["hakuilmoitukset"][0]
    item["kuvaus"] = {"fi": "", "sv": "", "en": ""}
    with _client(hae_pages={1: page}) as client:
        assert import_haeavustuksia(db_session, client).created == 1
    call = db_session.scalar(select(FundingCall))
    assert call.description is None
    call.evaluation.status = EvaluationStatus.REJECTED
    call.evaluation.rejected_at = datetime(2026, 10, 8, 12, 0)
    call.evaluation.suitability_score = 80
    call.evaluation.suitability_summary = "Tallennettu perustelu"
    call.evaluation.matched_keywords = ["koulutus"]
    call.evaluation.matched_excluded_keywords = []
    call.evaluation.ai_summary = "Tallennettu AI-teksti"
    call.participation = Participation(notes="Muistiinpano")
    db_session.commit()

    description = 'Koulutus ja vesienhoito. <script>alert("x")</script>'
    item["kuvaus"]["richFi"] = _document(description)
    with _client(hae_pages={1: page}) as client:
        assert import_haeavustuksia(db_session, client).updated == 1
        assert import_haeavustuksia(db_session, client).unchanged == 1
    db_session.refresh(call)
    assert call.description == description
    assert call.raw_data == item
    assert call.evaluation.status is EvaluationStatus.REJECTED
    assert call.evaluation.rejected_at == datetime(2026, 10, 8, 12, 0)
    assert call.evaluation.suitability_score == 80
    assert call.evaluation.suitability_summary == "Tallennettu perustelu"
    assert call.evaluation.matched_keywords == ["koulutus"]
    assert call.evaluation.matched_excluded_keywords == []
    assert call.evaluation.ai_summary == "Tallennettu AI-teksti"
    assert call.participation.notes == "Muistiinpano"
    with _test_client(db_session, monkeypatch) as client:
        details = _page_client(client.get("/hankkeet"))
        html = next(element for element in details.elements.values() if isinstance(element, ui.html))
        assert html.content == '<strong>Koulutus</strong> ja vesienhoito. &lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;'
