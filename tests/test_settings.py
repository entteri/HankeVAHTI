from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models import (
    EuraSearchCriteria,
    Evaluation,
    EvaluationStatus,
    FundingCall,
    Participation,
    SearchProfile,
)
from app.services.settings import delete_all_funding_calls, funding_call_count


def _row_count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_reset_removes_calls_and_related_decisions_but_keeps_search_settings(db_session):
    first = FundingCall(source="EURA", source_id="first", title="Ensimmäinen")
    first.evaluation = Evaluation(status=EvaluationStatus.PARTICIPATE)
    first.participation = Participation(notes="Testimuistiinpano")
    second = FundingCall(source="HAEAVUSTUKSIA", source_id="second", title="Toinen")
    second.evaluation = Evaluation(status=EvaluationStatus.REJECTED)
    db_session.add_all([first, second, SearchProfile(name="Oma haku"), EuraSearchCriteria(fund="ESR+")])
    db_session.commit()

    assert funding_call_count(db_session) == 2
    assert delete_all_funding_calls(db_session) == 2
    assert _row_count(db_session, FundingCall) == 0
    assert _row_count(db_session, Evaluation) == 0
    assert _row_count(db_session, Participation) == 0
    assert _row_count(db_session, SearchProfile) == 1
    assert _row_count(db_session, EuraSearchCriteria) == 1
    assert delete_all_funding_calls(db_session) == 0

    db_session.expunge_all()
    db_session.add(FundingCall(source="EURA", source_id="first", title="Uusi tuonti"))
    db_session.commit()
    assert funding_call_count(db_session) == 1


def test_settings_page_shows_reset_action_and_confirmation(db_session, monkeypatch):
    db_session.add(FundingCall(source="EURA", source_id="first", title="Testihanke"))
    db_session.commit()
    monkeypatch.setattr("app.ui.settings.SessionLocal", sessionmaker(bind=db_session.get_bind()))

    with TestClient(app) as client:
        response = client.get("/asetukset")

    assert response.status_code == 200
    assert "Tallennettuja hankkeita: 1" in response.text
    assert "Poista kaikki haetut hankkeet" in response.text
    assert "Poistetaanko kaikki haetut hankkeet?" in response.text
    assert funding_call_count(db_session) == 1
