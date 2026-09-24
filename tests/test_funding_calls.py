from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.main import app
from app.models import EvaluationStatus, FundingCall, Participation
from app.services.funding_calls import dashboard_counts


@contextmanager
def _test_client(db_session, monkeypatch):
    engine = db_session.get_bind()
    session_factory = sessionmaker(bind=engine)

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr("app.ui.dashboard.SessionLocal", session_factory)
    monkeypatch.setattr("app.ui.funding_calls.SessionLocal", session_factory)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def _add_calls(session, count=1):
    for index in range(count):
        session.add(FundingCall(source="EURA", source_id=f"call-{index}", title=f"Testihanke {index}"))
    session.commit()


def test_api_lists_searches_and_paginates_calls(db_session, monkeypatch):
    _add_calls(db_session, 25)
    with _test_client(db_session, monkeypatch) as client:
        first = client.get("/api/funding-calls")
        second = client.get("/api/funding-calls?page=2")
        search = client.get("/api/funding-calls?search=Testihanke%2024")
        review = client.get("/api/funding-calls?status=NEW")
    assert first.status_code == 200
    assert first.json()["total"] == 25
    assert len(first.json()["items"]) == 20
    assert len(second.json()["items"]) == 5
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["title"] == "Testihanke 24"
    assert review.json()["total"] == 25


def test_participation_decision_moves_call_out_of_review_queue(db_session, monkeypatch):
    _add_calls(db_session)
    call_id = db_session.scalar(select(FundingCall.id))
    with _test_client(db_session, monkeypatch) as client:
        decision = client.patch(f"/api/funding-calls/{call_id}/status", json={"status": "PARTICIPATE"})
        repeated = client.patch(f"/api/funding-calls/{call_id}/status", json={"status": "PARTICIPATE"})
        review = client.get("/api/funding-calls?status=NEW")
        participating = client.get("/api/funding-calls?status=PARTICIPATE")
        details = client.get(f"/api/funding-calls/{call_id}")
        ongoing_page = client.get("/kaynnissa")
    assert decision.status_code == 200
    assert decision.json()["participation_stage"] == "NOT_STARTED"
    assert repeated.status_code == 200
    assert review.json()["total"] == 0
    assert participating.json()["total"] == 1
    assert details.json()["title"] == "Testihanke 0"
    assert "Testihanke 0" in ongoing_page.text
    assert db_session.scalar(select(func.count()).select_from(Participation)) == 1
    assert dashboard_counts(db_session)["ongoing"] == 1


def test_rejection_moves_call_to_rejected_list(db_session, monkeypatch):
    _add_calls(db_session)
    call_id = db_session.scalar(select(FundingCall.id))
    with _test_client(db_session, monkeypatch) as client:
        decision = client.patch(f"/api/funding-calls/{call_id}/status", json={"status": "REJECTED"})
        review = client.get("/api/funding-calls?status=NEW")
        rejected = client.get("/api/funding-calls?status=REJECTED")
        rejected_page = client.get("/hylatyt")
    assert decision.status_code == 200
    assert decision.json()["status"] == "REJECTED"
    assert review.json()["total"] == 0
    assert rejected.json()["total"] == 1
    assert "Testihanke 0" in rejected_page.text
    assert db_session.scalar(select(func.count()).select_from(Participation)) == 0
    assert dashboard_counts(db_session)["rejected"] == 1


def test_review_page_shows_imported_calls_and_actions(db_session, monkeypatch):
    _add_calls(db_session)
    with _test_client(db_session, monkeypatch) as client:
        dashboard = client.get("/")
        review_page = client.get("/arvioi")
        all_page = client.get("/hankkeet")
    assert "Kaikki hankkeet" in dashboard.text
    assert "Testihanke 0" in review_page.text
    assert "Osallistu" in review_page.text
    assert "Hylkää" in review_page.text
    assert "Lisätiedot" in review_page.text
    assert "Testihanke 0" in all_page.text


def test_missing_call_returns_404_and_bad_status_returns_422(db_session, monkeypatch):
    with _test_client(db_session, monkeypatch) as client:
        assert client.get("/api/funding-calls/999").status_code == 404
        assert client.patch("/api/funding-calls/999/status", json={"status": "REJECTED"}).status_code == 404
        assert client.patch("/api/funding-calls/999/status", json={"status": "UNKNOWN"}).status_code == 422


def test_switching_decision_keeps_existing_participation_notes(db_session, monkeypatch):
    _add_calls(db_session)
    call_id = db_session.scalar(select(FundingCall.id))
    with _test_client(db_session, monkeypatch) as client:
        client.patch(f"/api/funding-calls/{call_id}/status", json={"status": "PARTICIPATE"})
        participation = db_session.scalar(select(Participation))
        participation.notes = "Sovittu palaveri"
        db_session.commit()
        client.patch(f"/api/funding-calls/{call_id}/status", json={"status": "REJECTED"})
        client.patch(f"/api/funding-calls/{call_id}/status", json={"status": "PARTICIPATE"})
    db_session.expire_all()
    assert db_session.scalar(select(Participation)).notes == "Sovittu palaveri"
    assert db_session.scalar(select(func.count()).select_from(Participation)) == 1
    assert dashboard_counts(db_session)["ongoing"] == 1
