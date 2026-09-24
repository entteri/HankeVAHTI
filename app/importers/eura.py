"""EURA 2021 -hakuilmoitusten jäsennys ja tuonti."""

import json
from datetime import date
from html.parser import HTMLParser
from urllib.parse import unquote

import httpx
from sqlalchemy.orm import Session

from app.importers.common import FundingCallData, ImportResult, upsert_calls
from app.services.eura_criteria import EuraCriteria, get_eura_criteria

EURA_URL = "https://eura2021.fi/hakuilmoitukset/"


def eura_detail_url(source_id: str) -> str:
    return f"{EURA_URL}hakuilmoitus/{source_id}/"


class _PreactDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._inside_data = False
        self._parts: list[str] = []
        self.payload: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and dict(attrs).get("type") == "__PREACT_CLI_DATA__":
            self._inside_data = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._inside_data:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._inside_data:
            self.payload = "".join(self._parts)
            self._inside_data = False


def _page_data(html: str) -> dict:
    parser = _PreactDataParser()
    parser.feed(html)
    if not parser.payload:
        raise ValueError("EURA-sivulta puuttuu __PREACT_CLI_DATA__")

    return json.loads(unquote(parser.payload))["preRenderData"]


def parse_eura_options(html: str) -> dict[str, dict[str, str]]:
    codes = _page_data(html)["koodisto"]
    result = {}
    for field, source_field in (
        ("fund", "rahasto"),
        ("area", "alue"),
        ("authority", "viranomainen"),
        ("regions", "maakunta"),
    ):
        result[field] = {
            str(code): value.get("fi") or str(code)
            for code, value in codes[source_field].items()
        }
    return result


def parse_eura_page(html: str, criteria: EuraCriteria | None = None) -> list[FundingCallData]:
    criteria = criteria or EuraCriteria()
    data = _page_data(html)
    items = data["hankehaku"]
    if not isinstance(items, list):
        raise ValueError("EURA:n hankehaku ei ole lista")

    calls = []
    for item in items:
        if item["tila"] != "haettavissa":
            continue
        if criteria.fund and item.get("rahasto") != criteria.fund:
            continue
        if criteria.area and item.get("alue") != criteria.area:
            continue
        if criteria.authority and item.get("viranomainen") != criteria.authority:
            continue
        if criteria.regions and not set(criteria.regions).intersection(item.get("maakunnat") or []):
            continue
        if criteria.call_identifier and criteria.call_identifier.casefold() not in (item.get("hakutunnus") or "").casefold():
            continue
        dates = item["hakuaika"]
        calls.append(
            FundingCallData(
                source="EURA",
                source_id=str(item["id"]),
                call_identifier=item.get("hakutunnus"),
                title=item["otsikko"].strip(),
                fund=item["rahasto"],
                source_url=eura_detail_url(str(item["id"])),
                application_start_date=date.fromisoformat(dates["alku"]) if dates.get("alku") else None,
                application_end_date=date.fromisoformat(dates["loppu"]) if dates.get("loppu") else None,
                raw_data=item,
            )
        )
    return calls


def fetch_eura_options(client: httpx.Client) -> dict[str, dict[str, str]]:
    response = client.get(EURA_URL)
    response.raise_for_status()
    return parse_eura_options(response.text)


def fetch_eura_calls(client: httpx.Client, criteria: EuraCriteria | None = None) -> list[FundingCallData]:
    response = client.get(EURA_URL)
    response.raise_for_status()
    return parse_eura_page(response.text, criteria)


def import_eura(session: Session, client: httpx.Client | None = None) -> ImportResult:
    """Tuo hakuehtoihin sopivat avoimet haut yhdessä transaktiossa."""
    try:
        criteria = get_eura_criteria(session)
        if client is None:
            with httpx.Client(timeout=30.0, follow_redirects=True) as owned_client:
                calls = fetch_eura_calls(owned_client, criteria)
        else:
            calls = fetch_eura_calls(client, criteria)
        result = upsert_calls(session, calls)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
