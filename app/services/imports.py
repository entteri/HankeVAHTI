"""Molempien tietolähteiden tuonti yhtenä tietokantatransaktiona."""

from dataclasses import asdict

import httpx
from sqlalchemy.orm import Session

from app.importers.common import upsert_calls
from app.importers.eura import fetch_eura_calls
from app.importers.haeavustuksia import fetch_haeavustuksia_calls
from app.services.eura_criteria import get_eura_criteria
from app.services.haeavustuksia_criteria import get_haeavustuksia_criteria


def run_imports(session: Session, client: httpx.Client | None = None) -> dict[str, dict[str, int]]:
    try:
        eura_criteria = get_eura_criteria(session)
        hae_criteria = get_haeavustuksia_criteria(session)
        if client is None:
            with httpx.Client(timeout=30.0, follow_redirects=True) as owned_client:
                eura_calls = fetch_eura_calls(owned_client, eura_criteria)
                hae_calls = fetch_haeavustuksia_calls(owned_client, criteria=hae_criteria)
        else:
            eura_calls = fetch_eura_calls(client, eura_criteria)
            hae_calls = fetch_haeavustuksia_calls(client, criteria=hae_criteria)

        result = {
            "eura": asdict(upsert_calls(session, eura_calls)),
            "haeavustuksia": asdict(upsert_calls(session, hae_calls)),
        }
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
