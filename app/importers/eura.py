"""EURA 2021 -hakuilmoitusten jäsennys ja tuonti."""

import json
from datetime import date
from html.parser import HTMLParser
from urllib.parse import unquote

import httpx
from sqlalchemy.orm import Session

from app.importers.common import FundingCallData, ImportResult, upsert_calls

EURA_URL = "https://eura2021.fi/hakuilmoitukset/"


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


def parse_eura_page(html: str) -> list[FundingCallData]:
    parser = _PreactDataParser()
    parser.feed(html)
    if not parser.payload:
        raise ValueError("EURA-sivulta puuttuu __PREACT_CLI_DATA__")

    data = json.loads(unquote(parser.payload))
    items = data["preRenderData"]["hankehaku"]
    if not isinstance(items, list):
        raise ValueError("EURA:n hankehaku ei ole lista")

    calls = []
    for item in items:
        if item["tila"] != "haettavissa" or item["rahasto"] != "ESR+":
            continue
        dates = item["hakuaika"]
        calls.append(
            FundingCallData(
                source="EURA",
                source_id=str(item["id"]),
                call_identifier=item.get("hakutunnus"),
                title=item["otsikko"].strip(),
                fund=item["rahasto"],
                source_url=EURA_URL,
                application_start_date=date.fromisoformat(dates["alku"]) if dates.get("alku") else None,
                application_end_date=date.fromisoformat(dates["loppu"]) if dates.get("loppu") else None,
                raw_data=item,
            )
        )
    return calls


def fetch_eura_calls(client: httpx.Client) -> list[FundingCallData]:
    response = client.get(EURA_URL)
    response.raise_for_status()
    return parse_eura_page(response.text)


def import_eura(session: Session, client: httpx.Client | None = None) -> ImportResult:
    """Tuo avoimet ESR+-haut. Koko tuonti tallentuu yhdessä transaktiossa."""
    try:
        if client is None:
            with httpx.Client(timeout=30.0, follow_redirects=True) as owned_client:
                calls = fetch_eura_calls(owned_client)
        else:
            calls = fetch_eura_calls(client)
        result = upsert_calls(session, calls)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
