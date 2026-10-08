import unicodedata
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser

import pytest
from nicegui import ui

from app.evaluators.relevance import evaluate_relevance
from app.models import Evaluation, EvaluationStatus, FundingCall, Participation, ParticipationStage
from app.services.funding_calls import get_funding_call
from app.services.relevance import score_funding_calls
from app.services.search_profiles import save_keyword_settings
from app.ui.keyword_highlights import highlight_keywords
from tests.test_funding_calls import _test_client
from tests.test_relevance_ui import _page_client


@pytest.mark.parametrize("text,words,expected", [
    ("Tekoäly ja TEKOÄLY", ["tekoäly"], "<strong>Tekoäly</strong> ja <strong>TEKOÄLY</strong>"),
    ("Taidot, aika ja AI-pilotti", ["AI"], "Taidot, aika ja <strong>AI</strong>-pilotti"),
    ("Osaamisen\n  kehittäminen!", ["osaamisen kehittäminen"], "<strong>Osaamisen\n  kehittäminen</strong>!"),
    ("Osaamisen kehittämistä", ["osaamisen kehittäminen"], "Osaamisen kehittämistä"),
    ("C++ ja (AI)", ["C++", "AI"], "<strong>C++</strong> ja (<strong>AI</strong>)"),
    ("AI koulutus", ["AI", "AI koulutus", "koulutus"], "<strong>AI koulutus</strong>"),
    ("Straße", ["STRASSE"], "<strong>Straße</strong>"),
    ("Kuvaus ilman osumia", ["tekoäly"], "Kuvaus ilman osumia"),
    ("", ["tekoäly"], ""),
])
def test_highlighting_matches_evaluator_and_preserves_text(text, words, expected):
    result = highlight_keywords(text, words)
    assert result == expected
    assert unescape(result.replace("<strong>", "").replace("</strong>", "")) == text
    assert ("<strong>" in result) == bool(evaluate_relevance([text], words, []).matched_keywords)


def test_decomposed_unicode_retains_original_spelling():
    text = unicodedata.normalize("NFD", "TEKOÄLY")
    assert highlight_keywords(text, ["tekoäly"]) == f"<strong>{text}</strong>"


def test_external_html_and_matched_html_are_escaped():
    text = '<script>alert("x")</script> <img src=x onerror=alert(1)> & AI'
    result = highlight_keywords(text, ['<script>alert("x")</script>', "AI"])
    assert '<strong>&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;</strong>' in result
    assert "&lt;img src=x onerror=alert(1)&gt; &amp; <strong>AI</strong>" in result
    tags = []
    parser = HTMLParser()
    parser.handle_starttag = lambda tag, attrs: tags.append((tag, attrs))
    parser.feed(result)
    assert tags == [("strong", []), ("strong", [])]
    assert highlight_keywords(text, []) == result.replace("<strong>", "").replace("</strong>", "")


@pytest.mark.parametrize("status", list(EvaluationStatus))
def test_scoring_persists_matches_and_preserves_decisions_and_participation(db_session, status):
    call = FundingCall(source="EURA", source_id="1", title="Koulutus", description="Tekoäly ja rakentaminen",
                       evaluation=Evaluation(status=status, ai_summary="Säilyvä AI-teksti",
                                             rejected_at=datetime(2026, 10, 8, 6, 34, tzinfo=timezone.utc)
                                             if status is EvaluationStatus.REJECTED else None),
                       participation=Participation(stage=ParticipationStage.PLANNING, notes="Muistiinpano",
                                                   responsible_person="Risto", next_action="Palaveri"))
    db_session.add(call)
    db_session.commit()
    rejected_at = call.evaluation.rejected_at
    save_keyword_settings(db_session, ["koulutus", "tekoäly"], ["rakentaminen"])
    assert score_funding_calls(db_session) == 1
    db_session.expire_all()
    assert call.evaluation.matched_keywords == ["koulutus", "tekoäly"]
    assert call.evaluation.matched_excluded_keywords == ["rakentaminen"]
    assert call.evaluation.suitability_score == 20
    save_keyword_settings(db_session, ["puuttuva"], ["puuttuva"])
    # Muuttunut profiili ei muuta tallennetun pisteytyksen osumia.
    assert get_funding_call(db_session, call.id).matched_keywords == ["koulutus", "tekoäly"]
    assert score_funding_calls(db_session) == 1
    db_session.expire_all()
    assert call.evaluation.matched_keywords == []
    assert call.evaluation.matched_excluded_keywords == []
    assert call.evaluation.status is status
    assert call.evaluation.rejected_at == rejected_at
    assert call.evaluation.ai_summary == "Säilyvä AI-teksti"
    assert call.participation.stage is ParticipationStage.PLANNING
    assert call.participation.notes == "Muistiinpano"
    assert call.participation.responsible_person == "Risto"
    assert call.participation.next_action == "Palaveri"


def test_ui_uses_stored_matches_in_badges_and_safe_description(db_session, monkeypatch):
    call = FundingCall(source="EURA", source_id="1", title="Koulutus",
                       description='<script>alert("x")</script> TEKOÄLY ja rakentaminen')
    db_session.add(call)
    db_session.commit()
    save_keyword_settings(db_session, ["koulutus", "tekoäly"], ["rakentaminen"])
    score_funding_calls(db_session)
    save_keyword_settings(db_session, ["rakentaminen"], [])
    with _test_client(db_session, monkeypatch) as client:
        page = _page_client(client.get("/hankkeet"))
        labels = [e.text for e in page.elements.values() if isinstance(e, ui.label)]
        assert "Osuneet hakusanat" in labels and "Poissulkevat osumat" in labels
        badges = [e.text for e in page.elements.values() if isinstance(e, ui.badge)]
        assert all(word in badges for word in ["koulutus", "tekoäly", "rakentaminen"])
        description = next(e for e in page.elements.values() if isinstance(e, ui.html))
        assert description.content == '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; <strong>TEKOÄLY</strong> ja rakentaminen'
        assert description.props["sanitize"] is True
        payload = client.get(f"/api/funding-calls/{call.id}").json()
        assert payload["matched_keywords"] == ["koulutus", "tekoäly"]
        assert payload["matched_excluded_keywords"] == ["rakentaminen"]
        assert payload["description"] == call.description


@pytest.mark.parametrize("mode,message", [
    ("legacy_score", "Osumatietoja ei ole tallennettu. Valitse Asetukset → Pisteytä kaikki haut, jotta myös päättyneiden hakujen osumat päivittyvät."),
    ("legacy_summary", "Osumatietoja ei ole tallennettu. Valitse Asetukset → Pisteytä kaikki haut, jotta myös päättyneiden hakujen osumat päivittyvät."),
    ("empty", "Ei osumia"),
    ("unscored", "Ei vielä pisteytetty"),
    ("no_evaluation", "Ei vielä pisteytetty"),
])
def test_ui_distinguishes_unknown_empty_and_unscored_matches(db_session, monkeypatch, mode, message):
    call = FundingCall(source="EURA", source_id="1", title="Haku", description="tekoäly")
    if mode != "no_evaluation":
        call.evaluation = Evaluation(
            suitability_score=0 if mode in ("legacy_score", "empty") else None,
            suitability_summary="Osuvat hakusanat: tekoäly" if mode == "legacy_summary" else None,
            matched_keywords=[] if mode == "empty" else None,
            matched_excluded_keywords=[] if mode == "empty" else None,
        )
    db_session.add(call)
    db_session.commit()
    with _test_client(db_session, monkeypatch) as client:
        page = _page_client(client.get("/hankkeet"))
        assert message in [e.text for e in page.elements.values() if isinstance(e, ui.label)]
        description = next(e for e in page.elements.values() if isinstance(e, ui.html))
        assert description.content == "tekoäly"
        payload = client.get("/api/funding-calls").json()["items"][0]
        assert payload["matched_keywords"] == ([] if mode == "empty" else None)
        assert payload["matched_excluded_keywords"] == ([] if mode == "empty" else None)
        assert payload["rejected_at"] is None
