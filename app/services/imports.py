"""Molempien tietolähteiden tuonti yhtenä tietokantatransaktiona."""

from dataclasses import asdict
from datetime import datetime
from typing import Literal, overload
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.importers.common import upsert_calls
from app.importers.eura import fetch_eura_calls
from app.importers.haeavustuksia import fetch_haeavustuksia_calls
from app.models import FundingCall, NotificationHistory, NotificationRun
from app.services.eura_criteria import get_eura_criteria
from app.services.haeavustuksia_criteria import get_haeavustuksia_criteria


@overload
def run_imports(
    session: Session, client: httpx.Client | None = None, *, include_created_ids: Literal[False] = False,
) -> dict[str, dict[str, int]]: ...


@overload
def run_imports(
    session: Session, client: httpx.Client | None = None, *, include_created_ids: Literal[True],
) -> dict[str, dict[str, int | list[int]]]: ...


def run_imports(
    session: Session,
    client: httpx.Client | None = None,
    *,
    include_created_ids: bool = False,
    notification_run_id: int | None = None,
) -> dict[str, dict[str, int | list[int]]]:
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

        source_results = {
            "eura": upsert_calls(session, eura_calls),
            "haeavustuksia": upsert_calls(session, hae_calls),
        }
        if notification_run_id is not None:
            run = session.get(NotificationRun, notification_run_id)
            if run is None or run.status != "IMPORTING":
                raise ValueError("Ilmoitusajo ei ole tuontitilassa.")
            fetched_ids = {
                call_id
                for result in source_results.values()
                for call_id in result.fetched_ids
            }
            if fetched_ids:
                existing_history_ids = set(session.scalars(
                    select(NotificationHistory.funding_call_id).where(
                        NotificationHistory.funding_call_id.in_(fetched_ids)
                    )
                ))
                today = datetime.now(ZoneInfo("Europe/Helsinki")).date()
                calls = session.scalars(
                    select(FundingCall).where(FundingCall.id.in_(fetched_ids))
                )
                session.add_all(
                    NotificationHistory(
                        funding_call_id=call.id,
                        run_id=notification_run_id,
                        status="PENDING_EVALUATION",
                    )
                    for call in calls
                    if call.id not in existing_history_ids
                    and (call.application_end_date is None or call.application_end_date >= today)
                )
            run.status = "EVALUATING"
            run.phase = "evaluation"
            run.last_error = None
        result = {}
        for source, import_result in source_results.items():
            values = asdict(import_result)
            values.pop("fetched_ids")
            if not include_created_ids:
                values.pop("created_ids")
            result[source] = values
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
