"""Haeavustuksia.fi:n sivutetun hankelistan tuonti."""

from datetime import date, datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

from app.importers.common import FundingCallData, ImportResult, upsert_calls
from app.services.haeavustuksia_criteria import HaeavustuksiaCriteria, get_haeavustuksia_criteria

API_URL = "https://www.haeavustuksia.fi/api/haku/list-items"
AUTHORITIES_URL = "https://www.haeavustuksia.fi/api/haku/valtionapuviranomaiset"
HAE_BASE_URL = "https://www.haeavustuksia.fi/fi/haku/"
HELSINKI = ZoneInfo("Europe/Helsinki")


def hae_detail_url(source_id: str) -> str:
    return HAE_BASE_URL + quote(source_id, safe="")


def _rich_text(value: object) -> str | None:
    """Lue richFi/richSv/richEn-dokumentin tekstisolmut tavallisena tekstinä."""
    parts: list[str] = []

    def visit(node: object) -> None:
        if not isinstance(node, dict):
            return
        kind = node.get("type")
        if kind == "text":
            if isinstance(node.get("text"), str):
                parts.append(node["text"])
            return
        if kind == "hardBreak":
            parts.append("\n")
            return
        children = node.get("content")
        if isinstance(children, list):
            for child in children:
                visit(child)
        if kind in ("paragraph", "heading", "listItem", "blockquote", "codeBlock", "tableRow"):
            parts.append("\n")
        elif kind in ("tableCell", "tableHeader"):
            parts.append("\t")

    visit(value)
    return "\n".join(line.strip() for line in "".join(parts).splitlines() if line.strip()) or None


def _localized_text(value: dict | str | None) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for language in ("fi", "sv", "en"):
            text = value.get(language)
            if isinstance(text, str) and text.strip():
                return text.strip()
            rich_text = _rich_text(value.get(f"rich{language.title()}"))
            if rich_text:
                return rich_text
    return None


def _local_date(value: str | None) -> date | None:
    if not value:
        return None
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("Haeavustuksia-päivämäärältä puuttuu aikavyöhyke")
    return timestamp.astimezone(HELSINKI).date()


def _parse_item(item: dict) -> FundingCallData:
    identifier = item["hakuasianAsianumero"]
    title = _localized_text(item.get("nimi"))
    if not identifier or not title:
        raise ValueError("Haeavustuksia-riviltä puuttuu asianumero tai nimi")
    return FundingCallData(
        source="HAEAVUSTUKSIA",
        source_id=str(identifier),
        call_identifier=str(identifier),
        title=title,
        description=_localized_text(item.get("kuvaus")),
        source_url=hae_detail_url(str(identifier)),
        application_start_date=_local_date(item.get("hakuAlkaaDateTimeUtc")),
        application_end_date=_local_date(item.get("hakuPaattyyDateTimeUtc")),
        raw_data=item,
    )


def fetch_haeavustuksia_authorities(client: httpx.Client) -> dict[str, str]:
    response = client.get(AUTHORITIES_URL)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise ValueError("Haeavustuksia-viranomaislista on virheellinen")
    options = {}
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("lyhenne"), str):
            raise ValueError("Haeavustuksia-viranomaislista on virheellinen")
        name = _localized_text(item.get("nimi"))
        if not name:
            raise ValueError("Haeavustuksia-viranomaiselta puuttuu nimi")
        options[item["lyhenne"]] = name
    return options


def fetch_haeavustuksia_calls(
    client: httpx.Client,
    page_size: int = 20,
    criteria: HaeavustuksiaCriteria | None = None,
) -> list[FundingCallData]:
    if page_size < 1:
        raise ValueError("Sivukoon on oltava positiivinen")
    criteria = criteria or HaeavustuksiaCriteria()

    # API accepts one authority and grant type per request. Fetch each selected
    # combination and collapse overlaps by source ID before writing to the DB.
    calls: dict[str, FundingCallData] = {}
    for authority in criteria.authorities or [""]:
        for grant_type in criteria.grant_types or [""]:
            page = 1
            while True:
                response = client.get(
                    API_URL,
                    params={
                        "Pagination.Page": page,
                        "Pagination.PageSize": page_size,
                        "Language": "fi",
                        "SearchTerm": "",
                        "VaOrgLyhenne": authority,
                        "ShowFuture": str(criteria.show_future).lower(),
                        "ShowOngoing": str(criteria.show_ongoing).lower(),
                        "ShowEnded": "false",
                        "HideExternal": "false",
                        **({"Avustuslaji": grant_type} if grant_type else {}),
                    },
                )
                response.raise_for_status()
                data = response.json()
                items = data["hakuilmoitukset"]
                page_count = data["pageCount"]
                if not isinstance(items, list) or not isinstance(page_count, int) or page_count < 0:
                    raise ValueError("Haeavustuksia-vastaus on virheellinen")
                for item in items:
                    call = _parse_item(item)
                    calls[call.source_id] = call
                if page >= page_count:
                    break
                page += 1
    return list(calls.values())


def import_haeavustuksia(session: Session, client: httpx.Client | None = None) -> ImportResult:
    """Tuo kaikki sivut ja tallenna tulos yhdessä transaktiossa."""
    try:
        criteria = get_haeavustuksia_criteria(session)
        if client is None:
            with httpx.Client(timeout=30.0, follow_redirects=True) as owned_client:
                calls = fetch_haeavustuksia_calls(owned_client, criteria=criteria)
        else:
            calls = fetch_haeavustuksia_calls(client, criteria=criteria)
        result = upsert_calls(session, calls)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
