"""Create a short AI summary for a selected funding call."""

import os
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT
from app.models import EvaluationStatus, FundingCall

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


class SummaryError(Exception):
    """A summary cannot be created or saved."""


def _read_context(path: Path) -> str:
    try:
        content = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise SummaryError(f"Tiedosto {path.name} puuttuu projektikansiosta.") from exc
    if not content:
        raise SummaryError(f"Tiedosto {path.name} on tyhjä.")
    return content


def _response_text(data: dict) -> str:
    if data.get("status") != "completed":
        raise SummaryError("Tekoäly ei saanut yhteenvetoa valmiiksi. Yritä uudelleen.")
    parts = [
        part.get("text", "")
        for item in data.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    ]
    summary = "\n".join(part.strip() for part in parts if part.strip()).strip()
    if not summary:
        raise SummaryError("Tekoäly ei palauttanut yhteenvetoa. Yritä uudelleen.")
    return summary


def generate_ai_summary(
    session: Session,
    call_id: int,
    *,
    client: httpx.Client | None = None,
    profile_path: Path | None = None,
    criteria_path: Path | None = None,
) -> str:
    """Read current local context, generate a summary, and save it separately from manual evaluations."""
    call = session.get(FundingCall, call_id)
    if call is None or call.evaluation is None or call.evaluation.status is not EvaluationStatus.PARTICIPATE:
        raise SummaryError("Hanketta ei löydy valituista hankkeista.")

    profile = _read_context(profile_path or PROJECT_ROOT / "asiakas.md")
    if criteria_path is None:
        criteria_path = PROJECT_ROOT / "arviokriteerit.md"
        if not criteria_path.exists():
            criteria_path = PROJECT_ROOT / "arviointikriteerit.md"
    criteria = _read_context(criteria_path)
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SummaryError("OPENAI_API_KEY puuttuu .env-tiedostosta.")

    instructions = (
        "Kirjoita suomeksi lyhyt, enintään kolmen virkkeen yhteenveto siitä, miksi hanke voisi sopia asiakkaalle. "
        "Vertaa hankkeen tavoitteita asiakkaan toimintaan, osaamiseen ja kumppaniverkostoon. "
        "Noudata annettuja arviointiohjeita ja perusta päätelmä vain annettuihin tietoihin. "
        "Mainitse yksi olennainen epävarmuus, jos tiedot eivät riitä varmaan arvioon. "
        "Älä väitä rahoituskelpoisuutta varmistetuksi. Palauta pelkkä yhteenvetoteksti."
    )
    input_text = (
        f"ARVIOINTIOHJEET JA ASIAKKAAN TOIMINTA\n{criteria}\n\nASIAKKAAN PROFIILI JA OSAAMINEN\n{profile}\n\n"
        f"HANKETIEDOT\nNimi: {call.title}\nLähde: {call.source}\nRahasto: {call.fund or 'Ei tiedossa'}\n"
        f"Luokka: {call.category or 'Ei tiedossa'}\nHakutunnus: {call.call_identifier or call.source_id}\n"
        f"Hakuaika: {call.application_start_date or 'Ei tiedossa'} – {call.application_end_date or 'Ei tiedossa'}\n"
        f"Kuvaus: {call.description or 'Ei saatavilla'}"
    )
    request = {
        "model": os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
        "instructions": instructions,
        "input": input_text,
        "max_output_tokens": 350,
        "store": False,
    }
    try:
        if client is None:
            with httpx.Client(timeout=60.0) as owned_client:
                response = owned_client.post(
                    OPENAI_RESPONSES_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=request,
                )
        else:
            response = client.post(
                OPENAI_RESPONSES_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=request,
            )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SummaryError("Tekoälypalveluun ei saatu yhteyttä. Tarkista API-avain ja yritä uudelleen.") from exc

    summary = _response_text(response.json())
    call.evaluation.ai_summary = summary
    session.commit()
    return summary
