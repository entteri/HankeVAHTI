import json
from datetime import date
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from sqlalchemy import func, select

from app.importers.eura import EURA_URL, eura_detail_url, import_eura, parse_eura_options, parse_eura_page
from app.importers.haeavustuksia import API_URL, hae_detail_url, import_haeavustuksia
from app.models import EvaluationStatus, FundingCall, Participation, ParticipationStage
from app.services.imports import run_imports
from app.services.eura_criteria import EuraCriteria, save_eura_criteria

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _eura_html(data: dict) -> str:
    payload = quote(json.dumps(data, ensure_ascii=False))
    return f'<html><script type="__PREACT_CLI_DATA__">{payload}</script></html>'


def _client(eura_data: dict | None = None, hae_pages: dict[int, dict] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == EURA_URL:
            return httpx.Response(200, text=_eura_html(eura_data))
        if request.url.path == "/api/haku/list-items":
            page = int(request.url.params["Pagination.Page"])
            assert request.url.params["Pagination.PageSize"] == "20"
            assert request.url.params["ShowFuture"] == "true"
            assert request.url.params["ShowOngoing"] == "true"
            assert request.url.params["ShowEnded"] == "false"
            return httpx.Response(200, json=hae_pages[page])
        raise AssertionError(f"Odottamaton osoite: {request.url}")

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_eura_parses_only_open_esr_calls():
    data = _fixture("eura_page_data.json")
    calls = parse_eura_page(_eura_html(data))
    assert len(calls) == 1
    assert calls[0].source_id == "d62b6d71-91c0-40e3-83b3-c5db0d51f134"
    assert calls[0].call_identifier == "PSUEVK-105"
    assert calls[0].application_end_date == date(2026, 9, 30)
    assert calls[0].source_url == eura_detail_url(calls[0].source_id)
    assert calls[0].raw_data == data["preRenderData"]["hankehaku"][0]


def test_eura_criteria_use_site_codes_and_filter_open_calls(db_session):
    data = _fixture("eura_page_data.json")
    html = _eura_html(data)
    options = parse_eura_options(html)
    assert options["fund"]["ESR+"] == "Euroopan sosiaalirahasto plus (ESR+)"
    assert options["regions"]["01"] == "Uusimaa"

    first = data["preRenderData"]["hankehaku"][0]
    first["hakutunnus"] = "PSUEVK-112"
    first["alue"] = "ETELA_SUOMI"
    first["viranomainen"] = "2601"
    first["maakunnat"] = ["01"]
    criteria = EuraCriteria(
        fund="ESR+",
        area="ETELA_SUOMI",
        authority="2601",
        regions=["01"],
        call_identifier="psuevk-112",
    )
    save_eura_criteria(db_session, criteria)
    with _client(eura_data=data) as client:
        assert import_eura(db_session, client).created == 1
    assert parse_eura_page(_eura_html(data), EuraCriteria(regions=["02"])) == []
    assert parse_eura_page(_eura_html(data), EuraCriteria(call_identifier="MISSING")) == []


def test_eura_fund_can_be_changed_to_other_site_option(db_session):
    data = _fixture("eura_page_data.json")
    save_eura_criteria(db_session, EuraCriteria(fund="EAKR"))
    with _client(eura_data=data) as client:
        assert import_eura(db_session, client).created == 1
    call = db_session.scalar(select(FundingCall))
    assert call.source_id == "eakr-1"
    assert call.fund == "EAKR"


def test_combined_import_uses_saved_eura_criteria(db_session):
    save_eura_criteria(db_session, EuraCriteria(fund="EAKR"))
    pages = {1: _fixture("hae_page_1.json"), 2: _fixture("hae_page_2.json")}
    with _client(eura_data=_fixture("eura_page_data.json"), hae_pages=pages) as client:
        result = run_imports(db_session, client)
    assert result["eura"]["created"] == 1
    assert db_session.scalar(select(FundingCall).where(FundingCall.source == "EURA")).source_id == "eakr-1"


def test_combined_import_applies_eura_filter_only_to_eura(db_session):
    save_eura_criteria(db_session, EuraCriteria(call_identifier="EI-LOYDY"))
    pages = {1: _fixture("hae_page_1.json"), 2: _fixture("hae_page_2.json")}
    with _client(eura_data=_fixture("eura_page_data.json"), hae_pages=pages) as client:
        result = run_imports(db_session, client)

    assert result["eura"]["created"] == 0
    assert result["haeavustuksia"]["created"] == 2
    assert db_session.scalar(select(func.count()).select_from(FundingCall)) == 2


def test_eura_missing_embedded_data_fails():
    with pytest.raises(ValueError, match="__PREACT_CLI_DATA__"):
        parse_eura_page("<html><body>Ei dataa</body></html>")


def test_eura_import_is_idempotent_and_preserves_user_data(db_session):
    data = _fixture("eura_page_data.json")
    with _client(eura_data=data) as client:
        assert import_eura(db_session, client).created == 1
        assert import_eura(db_session, client).unchanged == 1

    call = db_session.scalar(select(FundingCall).where(FundingCall.source == "EURA"))
    call.evaluation.status = EvaluationStatus.INTERESTING
    call.participation = Participation(stage=ParticipationStage.PLANNING, notes="Oma muistiinpano")
    db_session.commit()

    data["preRenderData"]["hankehaku"][0]["otsikko"] = "Päivitetty otsikko"
    with _client(eura_data=data) as client:
        assert import_eura(db_session, client).updated == 1
    db_session.refresh(call)
    assert call.title == "Päivitetty otsikko"
    assert call.evaluation.status is EvaluationStatus.INTERESTING
    assert call.participation.notes == "Oma muistiinpano"
    assert db_session.scalar(select(func.count()).select_from(FundingCall)) == 1


def test_hae_import_reads_all_pages_and_converts_local_dates(db_session):
    pages = {1: _fixture("hae_page_1.json"), 2: _fixture("hae_page_2.json")}
    with _client(hae_pages=pages) as client:
        result = import_haeavustuksia(db_session, client)
        second = import_haeavustuksia(db_session, client)
    assert (result.created, result.updated, result.unchanged) == (2, 0, 0)
    assert (second.created, second.updated, second.unchanged) == (0, 0, 2)

    first = db_session.scalar(select(FundingCall).where(FundingCall.source_id == "va-lou-2026-5"))
    assert first.call_identifier == "va-lou-2026-5"
    assert first.source_url == "https://www.haeavustuksia.fi/fi/haku/va-lou-2026-5"
    assert first.application_start_date == date(2026, 1, 1)
    assert first.application_end_date == date(2036, 12, 31)
    assert first.raw_data == pages[1]["hakuilmoitukset"][0]
    assert first.evaluation.status is EvaluationStatus.NEW


def test_hae_detail_url_escapes_path_segments():
    assert hae_detail_url("va/example") == "https://www.haeavustuksia.fi/fi/haku/va%2Fexample"


def test_hae_updates_source_data_without_overwriting_evaluation(db_session):
    pages = {1: _fixture("hae_page_1.json"), 2: _fixture("hae_page_2.json")}
    with _client(hae_pages=pages) as client:
        import_haeavustuksia(db_session, client)
    call = db_session.scalar(select(FundingCall).where(FundingCall.source_id == "va-bf-2026-12"))
    call.evaluation.status = EvaluationStatus.REJECTED
    db_session.commit()

    pages[2]["hakuilmoitukset"][0]["kuvaus"]["fi"] = "Uusi kuvaus"
    with _client(hae_pages=pages) as client:
        result = import_haeavustuksia(db_session, client)
    assert (result.created, result.updated, result.unchanged) == (0, 1, 1)
    db_session.refresh(call)
    assert call.description == "Uusi kuvaus"
    assert call.evaluation.status is EvaluationStatus.REJECTED


def test_combined_import_rolls_back_if_second_source_fails(db_session):
    data = _fixture("eura_page_data.json")

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == EURA_URL:
            return httpx.Response(200, text=_eura_html(data))
        if str(request.url).startswith(API_URL):
            return httpx.Response(503)
        raise AssertionError(request.url)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            run_imports(db_session, client)
    assert db_session.scalar(select(func.count()).select_from(FundingCall)) == 0


def test_combined_import_saves_both_sources(db_session):
    pages = {1: _fixture("hae_page_1.json"), 2: _fixture("hae_page_2.json")}
    with _client(eura_data=_fixture("eura_page_data.json"), hae_pages=pages) as client:
        result = run_imports(db_session, client)
    assert result["eura"]["created"] == 1
    assert result["haeavustuksia"]["created"] == 2
    assert db_session.scalar(select(func.count()).select_from(FundingCall)) == 3
