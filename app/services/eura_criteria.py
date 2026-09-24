"""EURA-hakuehtojen tallennus."""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import EuraSearchCriteria


@dataclass(frozen=True)
class EuraCriteria:
    fund: str | None = "ESR+"
    area: str | None = None
    authority: str | None = None
    regions: list[str] = field(default_factory=list)
    call_identifier: str | None = None


def get_eura_criteria(session: Session) -> EuraCriteria:
    row = session.get(EuraSearchCriteria, 1)
    if row is None:
        return EuraCriteria()
    return EuraCriteria(
        fund=row.fund,
        area=row.area,
        authority=row.authority,
        regions=list(row.regions),
        call_identifier=row.call_identifier,
    )


def save_eura_criteria(session: Session, criteria: EuraCriteria) -> None:
    row = session.get(EuraSearchCriteria, 1)
    if row is None:
        row = EuraSearchCriteria(id=1)
        session.add(row)
    row.fund = criteria.fund
    row.area = criteria.area
    row.authority = criteria.authority
    row.regions = list(criteria.regions)
    row.call_identifier = criteria.call_identifier.strip() or None if criteria.call_identifier else None
    session.commit()
