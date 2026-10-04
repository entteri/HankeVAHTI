from datetime import date

from app.models import Evaluation, EvaluationStatus, FundingCall, Participation, ParticipationStage
from app.services.duplicates import find_duplicate_matches
from tests.test_funding_calls import _test_client


def _call(source, source_id, title, *, start=None, end=None, identifier=None):
    return FundingCall(
        source=source,
        source_id=source_id,
        call_identifier=identifier,
        title=title,
        application_start_date=start,
        application_end_date=end,
        source_url=f"https://example.org/{source_id}",
    )


def test_cross_source_match_uses_title_and_dates_without_changing_decisions(db_session):
    eura = _call(
        "EURA", "eura-1", "Nuorten osaamisen kehittäminen",
        start=date(2026, 10, 1), end=date(2026, 11, 30),
    )
    hae = _call(
        "HAEAVUSTUKSIA", "hae-1", "Nuorten osaamisen  kehittäminen!",
        start=date(2026, 10, 2), end=date(2026, 11, 30),
    )
    eura.evaluation = Evaluation(status=EvaluationStatus.PARTICIPATE)
    eura.participation = Participation(stage=ParticipationStage.PLANNING, notes="Säilytettävä")
    db_session.add_all([eura, hae])
    db_session.commit()

    matches = find_duplicate_matches(db_session)

    assert len(matches) == 1
    assert (matches[0].eura.id, matches[0].haeavustuksia.id) == (eura.id, hae.id)
    assert "Samankaltainen nimi" in matches[0].reason
    assert eura.evaluation.status is EvaluationStatus.PARTICIPATE
    assert eura.participation.notes == "Säilytettävä"


def test_match_rejects_same_source_and_conflicting_dates(db_session):
    title = "Nuorten osaamisen kehittäminen"
    db_session.add_all([
        _call("EURA", "eura-1", title, end=date(2026, 11, 30)),
        _call("EURA", "eura-2", title, end=date(2026, 11, 30)),
        _call("HAEAVUSTUKSIA", "hae-1", title, end=date(2027, 1, 1)),
    ])
    db_session.commit()
    assert find_duplicate_matches(db_session) == []


def test_shared_cross_source_identifier_is_reported_even_if_titles_differ(db_session):
    db_session.add_all([
        _call("EURA", "eura-1", "Alueellinen koulutushaku", identifier="YHT-2026-15"),
        _call("HAEAVUSTUKSIA", "hae-1", "Koulutuksen avustushaku", identifier="yht 2026 15"),
    ])
    db_session.commit()
    assert find_duplicate_matches(db_session)[0].reason == "Sama hakutunnus molemmissa lähteissä."


def test_existing_calls_are_marked_on_dashboard_list_and_duplicate_page(db_session, monkeypatch):
    db_session.add_all([
        _call("EURA", "eura-1", "Nuorten osaamisen kehittäminen", end=date(2026, 11, 30)),
        _call("HAEAVUSTUKSIA", "hae-1", "Nuorten osaamisen kehittäminen", end=date(2026, 11, 30)),
    ])
    db_session.commit()
    with _test_client(db_session, monkeypatch) as client:
        dashboard = client.get("/")
        calls = client.get("/hankkeet")
        duplicates = client.get("/duplikaatit")
    assert dashboard.status_code == 200
    assert "Mahdollisia duplikaattipareja" in dashboard.text
    assert calls.text.count("Mahdollinen duplikaatti") >= 2
    assert duplicates.status_code == 200
    assert "Mahdollisia pareja: 1" in duplicates.text
    assert "EURA: Nuorten osaamisen kehittäminen" in duplicates.text
    assert "HAEAVUSTUKSIA: Nuorten osaamisen kehittäminen" in duplicates.text
