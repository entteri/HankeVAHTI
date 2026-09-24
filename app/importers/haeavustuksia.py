"""Haeavustuksia.fi:n sivutetun hankelistan tuonti."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

from app.importers.common import FundingCallData, ImportResult, upsert_calls

API_URL = "https://www.haeavustuksia.fi/api/haku/list-items"
HELSINKI = ZoneInfo("Europe/Helsinki")


def _localized_text(value: dict | str | None) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for language in ("fi", "sv", "en"):
            text = value.get(language)
            if isinstance(text, str) and text.strip():
                return text.strip()
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
        source_url=API_URL,
        application_start_date=_local_date(item.get("hakuAlkaaDateTimeUtc")),
        application_end_date=_local_date(item.get("hakuPaattyyDateTimeUtc")),
        raw_data=item,
    )


def fetch_haeavustuksia_calls(client: httpx.Client, page_size: int = 20) -> list[FundingCallData]:
    if page_size < 1:
        raise ValueError("Sivukoon on oltava positiivinen")

    calls = []
    page = 1
    while True:
        response = client.get(
            API_URL,
            params={
                "Pagination.Page": page,
                "Pagination.PageSize": page_size,
                "Language": "fi",
                "SearchTerm": "",
                "VaOrgLyhenne": "",
                "ShowFuture": "true",
                "ShowOngoing": "true",
                "ShowEnded": "false",
                "HideExternal": "false",
            },
        )
        response.raise_for_status()
        data = response.json()
        items = data["hakuilmoitukset"]
        page_count = data["pageCount"]
        if not isinstance(items, list) or not isinstance(page_count, int) or page_count < 0:
            raise ValueError("Haeavustuksia-vastaus on virheellinen")
        calls.extend(_parse_item(item) for item in items)
        if page >= page_count:
            break
        page += 1
    return calls


def import_haeavustuksia(session: Session, client: httpx.Client | None = None) -> ImportResult:
    """Tuo kaikki sivut ja tallenna tulos yhdessä transaktiossa."""
    try:
        if client is None:
            with httpx.Client(timeout=30.0, follow_redirects=True) as owned_client:
                calls = fetch_haeavustuksia_calls(owned_client)
        else:
            calls = fetch_haeavustuksia_calls(client)
        result = upsert_calls(session, calls)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
