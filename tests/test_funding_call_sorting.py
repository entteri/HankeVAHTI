import asyncio
from datetime import date, datetime, timezone

import pytest
from nicegui import ui
from sqlalchemy import select

from app.models import Evaluation, EvaluationStatus, FundingCall, Participation, ParticipationStage
from app.services.funding_calls import FundingCallSort, list_funding_calls
from tests.test_funding_calls import _test_client
from tests.test_relevance_ui import _click, _page_client


def _add_call(session, title, score=None, *, evaluation=True, status=EvaluationStatus.NEW, deadline=None):
    call = FundingCall(
        source="EURA", source_id=title, title=title, application_end_date=deadline,
        created_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
    )
    if evaluation:
        call.evaluation = Evaluation(status=status, suitability_score=score)
    session.add(call)
    session.flush()
    return call


@pytest.mark.parametrize("sort,expected", [
    (FundingCallSort.RELEVANCE_DESC, [100, 60, 0, None, None]),
    (FundingCallSort.RELEVANCE_ASC, [0, 60, 100, None, None]),
])
def test_relevance_sort_places_scored_calls_first_and_does_not_write(db_session, sort, expected):
    _add_call(db_session, "Puuttuva arvio", evaluation=False)
    _add_call(db_session, "Keskitaso", 60)
    _add_call(db_session, "Nolla", 0)
    _add_call(db_session, "Paras", 100)
    _add_call(db_session, "Puuttuva pistemäärä")
    db_session.commit()
    before = list(db_session.execute(select(Evaluation.id, Evaluation.status, Evaluation.suitability_score, Evaluation.updated_at)))
    calls, total = list_funding_calls(db_session, sort=sort)
    assert total == 5
    assert [call.suitability_score for call in calls] == expected
    assert calls[-1].title == "Puuttuva arvio"
    assert not db_session.new and not db_session.dirty and not db_session.deleted
    assert list(db_session.execute(select(Evaluation.id, Evaluation.status, Evaluation.suitability_score, Evaluation.updated_at))) == before


def test_deadline_sort_and_default_order(db_session):
    _add_call(db_session, "Myöhempi", deadline=date(2027, 2, 1))
    _add_call(db_session, "Lähin", deadline=date(2027, 1, 1))
    _add_call(db_session, "Ei päivää")
    db_session.commit()
    calls, _ = list_funding_calls(db_session, sort=FundingCallSort.DEADLINE_ASC)
    assert [call.title for call in calls] == ["Lähin", "Myöhempi", "Ei päivää"]
    default, _ = list_funding_calls(db_session)
    assert [call.title for call in default] == ["Ei päivää", "Lähin", "Myöhempi"]


def test_sort_applies_after_filters_and_before_pagination_with_stable_ties(db_session):
    _add_call(db_session, "Koulutus matala", 20)
    _add_call(db_session, "Koulutus korkea vanhempi", 80)
    _add_call(db_session, "Koulutus korkea uudempi", 80)
    _add_call(db_session, "Muu hanke", 100)
    _add_call(db_session, "Koulutus hylätty", 100, status=EvaluationStatus.REJECTED)
    db_session.commit()
    names = []
    for page in range(1, 4):
        calls, total = list_funding_calls(
            db_session, search="Koulutus", status=EvaluationStatus.NEW,
            sort=FundingCallSort.RELEVANCE_DESC, page=page, page_size=1,
        )
        assert total == 3
        names.append(calls[0].title)
    assert names == ["Koulutus korkea uudempi", "Koulutus korkea vanhempi", "Koulutus matala"]


def test_sort_preserves_ongoing_filter(db_session):
    for title, score, stage in [("Aktiivinen 20", 20, ParticipationStage.PLANNING),
                                ("Aktiivinen 80", 80, ParticipationStage.NOT_STARTED),
                                ("Valmis", 100, ParticipationStage.COMPLETED)]:
        call = _add_call(db_session, title, score, status=EvaluationStatus.PARTICIPATE)
        call.participation = Participation(stage=stage)
    db_session.commit()
    calls, total = list_funding_calls(db_session, ongoing_only=True, sort=FundingCallSort.RELEVANCE_DESC)
    assert total == 2
    assert [call.suitability_score for call in calls] == [80, 20]


def test_api_accepts_sort_with_filters_and_rejects_unknown_sort(db_session, monkeypatch):
    _add_call(db_session, "Koulutus 20", 20)
    _add_call(db_session, "Koulutus 80", 80)
    _add_call(db_session, "Muu", 100)
    db_session.commit()
    with _test_client(db_session, monkeypatch) as client:
        response = client.get("/api/funding-calls?sort=relevance_desc&search=Koulutus&status=NEW&page_size=1")
        assert response.status_code == 200
        assert response.json()["total"] == 2
        assert response.json()["items"][0]["suitability_score"] == 80
        assert client.get("/api/funding-calls?sort=unknown").status_code == 422


async def _change(page, kind, label, value):
    with page:
        element = next(e for e in page.elements.values() if isinstance(e, kind) and e.props.get("label") == label)
        before = asyncio.all_tasks()
        element.set_value(value)
        pending = asyncio.all_tasks() - before
        if pending:
            await asyncio.wait_for(asyncio.gather(*pending), timeout=5)


def _titles(page):
    # Otsikko on sekä dialogissa että kortissa; tarkista molempien yhteinen järjestys.
    return list(dict.fromkeys(e.text for e in page.elements.values()
                             if isinstance(e, ui.label) and e.text.startswith("Testihaku ") and " · " not in e.text))


def test_ui_sorts_filtered_results_and_keeps_sort_after_decisions(db_session, monkeypatch):
    _add_call(db_session, "Testihaku matala", 20)
    _add_call(db_session, "Testihaku korkea", 80)
    _add_call(db_session, "Muu", 100)
    db_session.commit()
    with _test_client(db_session, monkeypatch) as client:
        page = _page_client(client.get("/hankkeet"))
        client.portal.call(_change, page, ui.input, "Hae nimellä tai tunnuksella", "Testihaku")
        client.portal.call(_change, page, ui.select, "Tila", "NEW")
        client.portal.call(_change, page, ui.select, "Lajittelu", "relevance_asc")
        assert _titles(page) == ["Testihaku matala", "Testihaku korkea"]
        client.portal.call(_change, page, ui.select, "Lajittelu", "relevance_desc")
        assert _titles(page) == ["Testihaku korkea", "Testihaku matala"]
        client.portal.call(_click, page, "Osallistu")
        assert _titles(page) == ["Testihaku matala"]
        client.portal.call(_click, page, "Hylkää")
        assert _titles(page) == []
        client.portal.call(_change, page, ui.select, "Tila", "ALL")
        assert _titles(page) == ["Testihaku korkea", "Testihaku matala"]
    db_session.expire_all()
    calls = db_session.scalars(select(FundingCall).where(FundingCall.title.like("Testihaku %"))).all()
    assert {call.title: call.evaluation.status for call in calls} == {
        "Testihaku korkea": EvaluationStatus.PARTICIPATE,
        "Testihaku matala": EvaluationStatus.REJECTED,
    }


def test_ui_sort_resets_page_to_first(db_session, monkeypatch):
    for index in range(25):
        _add_call(db_session, f"Testihaku {index:02}", index)
    db_session.commit()
    with _test_client(db_session, monkeypatch) as client:
        page = _page_client(client.get("/hankkeet"))

        async def next_page():
            with page:
                pagination = next(e for e in page.elements.values() if isinstance(e, ui.pagination))
                before = asyncio.all_tasks()
                pagination.set_value(2)
                await asyncio.wait_for(asyncio.gather(*(asyncio.all_tasks() - before)), timeout=5)

        client.portal.call(next_page)
        assert len(_titles(page)) == 5
        client.portal.call(_change, page, ui.select, "Lajittelu", "relevance_asc")
        assert len(_titles(page)) == 20
        assert _titles(page)[0] == "Testihaku 00"
