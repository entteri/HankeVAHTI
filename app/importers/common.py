"""Lähdedatan tallennus ilman käyttäjän arvioiden muuttamista."""

from dataclasses import dataclass, field, fields
from datetime import date
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Evaluation, EvaluationStatus, FundingCall


@dataclass(frozen=True)
class FundingCallData:
    source: str
    source_id: str
    title: str
    raw_data: dict[str, Any]
    call_identifier: str | None = None
    description: str | None = None
    fund: str | None = None
    category: str | None = None
    source_url: str | None = None
    application_start_date: date | None = None
    application_end_date: date | None = None


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    created_ids: list[int] = field(default_factory=list)
    fetched_ids: list[int] = field(default_factory=list)


def upsert_calls(session: Session, calls: Iterable[FundingCallData]) -> ImportResult:
    """Tallenna lähdekentät; jätä Evaluation ja Participation koskematta."""
    result = ImportResult()
    created_rows: list[FundingCall] = []
    fetched_rows: list[FundingCall] = []
    for call in calls:
        existing = session.scalar(
            select(FundingCall).where(
                FundingCall.source == call.source,
                FundingCall.source_id == call.source_id,
            )
        )
        if existing is None:
            row = FundingCall(**{field.name: getattr(call, field.name) for field in fields(call)})
            row.evaluation = Evaluation(status=EvaluationStatus.NEW)
            session.add(row)
            created_rows.append(row)
            fetched_rows.append(row)
            result.created += 1
            continue

        changed = False
        for field in fields(call):
            if field.name in {"source", "source_id"}:
                continue
            value = getattr(call, field.name)
            if getattr(existing, field.name) != value:
                setattr(existing, field.name, value)
                changed = True
        if changed:
            result.updated += 1
        else:
            result.unchanged += 1
        fetched_rows.append(existing)
    if created_rows:
        session.flush()
        result.created_ids = [row.id for row in created_rows]
    result.fetched_ids = list(dict.fromkeys(row.id for row in fetched_rows))
    return result
