import unicodedata
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.evaluators.relevance import evaluate_relevance, relevance_label
from app.models import Evaluation, EvaluationStatus, FundingCall, Participation, ParticipationStage, SearchProfile
from app.services.relevance import score_funding_calls
from app.services.search_profiles import get_keyword_settings, save_keyword_settings


def test_interest_and_additional_keywords_increase_score():
    text = ["Tekoäly ja koulutus"]
    assert evaluate_relevance(text, [], []).score == 0
    assert evaluate_relevance(text, ["tekoäly"], []).score == 20
    assert evaluate_relevance(text, ["tekoäly", "koulutus"], []).score == 40


def test_exclusion_lowers_score_and_is_explained():
    result = evaluate_relevance(["Tekoäly, koulutus ja rakentaminen"], ["tekoäly", "koulutus"], ["rakentaminen"])
    assert result.score == 20
    assert result.matched_keywords == ("tekoäly", "koulutus")
    assert result.matched_excluded_keywords == ("rakentaminen",)
    assert "Osuvat hakusanat (2): tekoäly, koulutus" in result.summary
    assert "Poissulkevat osumat (1): rakentaminen" in result.summary
    assert "40 − 20" in result.summary


def test_score_is_capped_and_exclusions_apply_after_positive_cap():
    words = [f"sana{i}" for i in range(12)]
    text = [" ".join(words)]
    assert evaluate_relevance(text, words, []).score == 100
    assert evaluate_relevance(text, words, ["sana0"]).score == 80
    assert evaluate_relevance(text, words, words).score == 0


@pytest.mark.parametrize("texts", [[], [None, ""], ["Maataloushaku"]])
def test_no_matches_are_valid(texts):
    result = evaluate_relevance(texts, ["tekoäly"], ["rakentaminen"])
    assert result.score == 0
    assert result.matched_keywords == ()
    assert result.matched_excluded_keywords == ()
    assert "ei osumia" in result.summary


def test_case_accents_unicode_and_whitespace_are_normalized():
    text = unicodedata.normalize("NFD", "TEKOÄLY ja OSAAMISEN\n KEHITTÄMINEN")
    result = evaluate_relevance([text], ["tekoäly", "osaamisen kehittäminen"], [])
    assert result.score == 40


def test_whole_words_avoid_ai_false_positive_and_phrases_stay_within_fields():
    assert evaluate_relevance(["Taidot ja aika"], ["AI"], []).score == 0
    assert evaluate_relevance(["AI-pilotti (AI)"], ["AI"], []).score == 20
    assert evaluate_relevance(["osaamisen", "kehittäminen"], ["osaamisen kehittäminen"], []).score == 0
    assert evaluate_relevance(["koulutuksen"], ["koulutus"], []).score == 0


def test_repetitions_duplicates_and_regex_symbols_are_literal():
    result = evaluate_relevance(["AI AI AI ja C++"], ["AI", " ai ", "C++", ""], [])
    assert result.score == 40
    assert result.matched_keywords == ("AI", "C++")


@pytest.mark.parametrize("score,label", [
    (None, "Ei vielä pisteytetty"),
    (0, "Todennäköisesti ei relevantti"),
    (29, "Todennäköisesti ei relevantti"),
    (30, "Tarkistettava"),
    (59, "Tarkistettava"),
    (60, "Mahdollisesti relevantti"),
    (79, "Mahdollisesti relevantti"),
    (80, "Hyvin relevantti"),
    (100, "Hyvin relevantti"),
])
def test_relevance_class_boundaries(score, label):
    assert relevance_label(score) == label


def test_keyword_settings_can_be_added_changed_and_removed_without_touching_other_profiles(db_session):
    other = SearchProfile(name="Oma vanha profiili", keywords=["säilytettävä"], active=False)
    db_session.add(other)
    db_session.commit()
    assert get_keyword_settings(db_session).keywords == ()
    saved = save_keyword_settings(db_session, [" tekoäly ", "TEKOÄLY", "osaamisen   kehittäminen", ""], [" Tie "])
    db_session.expire_all()
    assert get_keyword_settings(db_session) == saved
    assert saved.keywords == ("tekoäly", "osaamisen kehittäminen")
    assert saved.excluded_keywords == ("Tie",)
    save_keyword_settings(db_session, ["koulutus"], [])
    assert get_keyword_settings(db_session).keywords == ("koulutus",)
    save_keyword_settings(db_session, [], [])
    assert get_keyword_settings(db_session).keywords == ()
    assert db_session.scalar(select(func.count()).select_from(SearchProfile)) == 2
    db_session.refresh(other)
    assert other.keywords == ["säilytettävä"]
    assert other.active is False


@pytest.mark.parametrize("status", list(EvaluationStatus))
def test_scoring_keeps_every_call_status_and_participation(db_session, status):
    call = FundingCall(source="EURA", source_id="1", title="Koulutus ja tekoäly", raw_data={"original": True})
    call.evaluation = Evaluation(status=status)
    call.participation = Participation(stage=ParticipationStage.PLANNING, notes="Muista palaveri", responsible_person="Testaaja")
    db_session.add(call)
    db_session.commit()
    save_keyword_settings(db_session, ["koulutus", "tekoäly"], ["koulutus"])
    assert score_funding_calls(db_session) == 1
    db_session.expire_all()
    stored = db_session.get(FundingCall, call.id)
    assert stored.evaluation.status is status
    assert stored.evaluation.suitability_score == 20
    assert "tekoäly" in stored.evaluation.suitability_summary
    assert stored.participation.stage is ParticipationStage.PLANNING
    assert stored.participation.notes == "Muista palaveri"
    assert stored.participation.responsible_person == "Testaaja"
    assert stored.raw_data == {"original": True}
    assert db_session.scalar(select(func.count()).select_from(FundingCall)) == 1


def test_batch_includes_today_future_and_unknown_end_but_preserves_ended_calls(db_session):
    today = date(2026, 9, 25)
    for index, end in enumerate([today - timedelta(days=1), today, today + timedelta(days=1), None]):
        call = FundingCall(source="EURA", source_id=str(index), title="Koulutus", application_end_date=end)
        if index == 0:
            call.evaluation = Evaluation(suitability_score=80, suitability_summary="Vanha arvio")
        db_session.add(call)
    db_session.commit()
    save_keyword_settings(db_session, ["koulutus"], [])
    assert score_funding_calls(db_session, as_of=today) == 3
    ended = db_session.scalar(select(FundingCall).where(FundingCall.source_id == "0"))
    assert ended.evaluation.suitability_score == 80
    assert ended.evaluation.suitability_summary == "Vanha arvio"
    assert db_session.scalar(select(func.count()).select_from(FundingCall)) == 4


def test_scoring_selected_ids_and_rescoring_after_keyword_change(db_session):
    first = FundingCall(source="EURA", source_id="1", title="Koulutus", description="tekoäly", fund="ESR+", category="digitaidot")
    second = FundingCall(source="EURA", source_id="2", title="Koulutus")
    db_session.add_all([first, second])
    db_session.commit()
    save_keyword_settings(db_session, ["tekoäly", "ESR+", "digitaidot"], [])
    assert score_funding_calls(db_session, call_ids=[]) == 0
    assert score_funding_calls(db_session, call_ids=[first.id]) == 1
    assert first.evaluation.status is EvaluationStatus.NEW
    assert first.evaluation.suitability_score == 60
    assert second.evaluation is None
    save_keyword_settings(db_session, [], [])
    assert first.evaluation.suitability_score == 60  # Tallennus ei pisteytä salaa uudelleen.
    assert score_funding_calls(db_session, call_ids=[first.id]) == 1
    assert first.evaluation.suitability_score == 0
    assert "ei osumia" in first.evaluation.suitability_summary


def test_no_saved_profile_does_not_modify_existing_evaluation(db_session):
    call = FundingCall(source="EURA", source_id="1", title="Koulutus")
    call.evaluation = Evaluation(status=EvaluationStatus.REJECTED, suitability_score=80)
    db_session.add(call)
    db_session.commit()
    with pytest.raises(ValueError, match="Tallenna"):
        score_funding_calls(db_session)
    db_session.refresh(call)
    assert call.evaluation.suitability_score == 80
    assert call.evaluation.status is EvaluationStatus.REJECTED


def test_scoring_failure_rolls_back_entire_batch(db_session, monkeypatch):
    for index in range(2):
        call = FundingCall(source="EURA", source_id=str(index), title="Koulutus")
        call.evaluation = Evaluation(status=EvaluationStatus.INTERESTING, suitability_score=80)
        db_session.add(call)
    db_session.commit()
    save_keyword_settings(db_session, ["koulutus"], [])
    runs = 0

    def fail_second(*args):
        nonlocal runs
        runs += 1
        if runs == 2:
            raise RuntimeError("Testivirhe")
        return evaluate_relevance(*args)

    monkeypatch.setattr("app.services.relevance.evaluate_relevance", fail_second)
    with pytest.raises(RuntimeError):
        score_funding_calls(db_session)
    db_session.expire_all()
    assert list(db_session.scalars(select(Evaluation.suitability_score))) == [80, 80]
