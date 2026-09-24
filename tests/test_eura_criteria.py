import json
from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models import EuraSearchCriteria, FundingCall
from app.services.eura_criteria import EuraCriteria, get_eura_criteria, save_eura_criteria
from app.services.funding_calls import get_funding_call


def test_criteria_default_and_saved_values(db_session):
    assert get_eura_criteria(db_session) == EuraCriteria()
    selected = EuraCriteria(
        fund=None,
        area="ETELA_SUOMI",
        authority="2601",
        regions=["01", "02"],
        call_identifier="PSUEVK-112",
    )
    save_eura_criteria(db_session, selected)
    assert get_eura_criteria(db_session) == selected
    assert db_session.scalar(select(EuraSearchCriteria)).fund is None


def test_existing_eura_call_gets_direct_detail_link(db_session):
    call = FundingCall(
        source="EURA",
        source_id="565ea41d-d19c-47aa-be8d-4d04e3287df6",
        call_identifier="PSUEVK-112",
        title="Jatkuva oppiminen",
        source_url="https://eura2021.fi/hakuilmoitukset/",
    )
    db_session.add(call)
    db_session.commit()
    view = get_funding_call(db_session, call.id)
    assert view.source_url == (
        "https://eura2021.fi/hakuilmoitukset/hakuilmoitus/"
        "565ea41d-d19c-47aa-be8d-4d04e3287df6/"
    )


def test_existing_hae_call_gets_direct_detail_link(db_session):
    call = FundingCall(
        source="HAEAVUSTUKSIA",
        source_id="va-lou-2026-5",
        call_identifier="va-lou-2026-5",
        title="Yksityisteiden valtionavustukset",
        source_url="https://www.haeavustuksia.fi/api/haku/list-items",
    )
    db_session.add(call)
    db_session.commit()
    view = get_funding_call(db_session, call.id)
    assert view.source_url == "https://www.haeavustuksia.fi/fi/haku/va-lou-2026-5"


def test_search_criteria_page_shows_eura_options(db_session, monkeypatch):
    data = json.loads((Path(__file__).parent / "fixtures" / "eura_page_data.json").read_text(encoding="utf-8"))
    payload = quote(json.dumps(data, ensure_ascii=False))
    html = f'<script type="__PREACT_CLI_DATA__">{payload}</script>'
    from app.importers.eura import parse_eura_options

    monkeypatch.setattr("app.ui.search_criteria.fetch_eura_options", lambda client: parse_eura_options(html))
    monkeypatch.setattr("app.ui.search_criteria.SessionLocal", sessionmaker(bind=db_session.get_bind()))
    with TestClient(app) as client:
        response = client.get("/hakuehdot")
    assert response.status_code == 200
    for label in ("Rahasto", "Haun kohdealue", "Viranomainen", "Maakunnat", "Hakutunnus", "Tallenna hakuehdot"):
        assert label in response.text
