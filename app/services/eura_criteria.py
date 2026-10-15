"""EURA-hakuehtojen tallennus."""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import EuraSearchCriteria


@dataclass(frozen=True)
class EuraCriteria:
    funds: list[str] = field(default_factory=lambda: ["ESR+"])
    areas: list[str] = field(default_factory=list)
    authorities: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    call_identifier: str | None = None


def get_eura_criteria(session: Session) -> EuraCriteria:
    row = session.get(EuraSearchCriteria, 1)
    if row is None:
        return EuraCriteria()
    return EuraCriteria(
        funds=list(row.funds),
        areas=list(row.areas),
        authorities=list(row.authorities),
        regions=list(row.regions),
        call_identifier=row.call_identifier,
    )


def save_eura_criteria(session: Session, criteria: EuraCriteria) -> None:
    row = session.get(EuraSearchCriteria, 1)
    if row is None:
        row = EuraSearchCriteria(id=1)
        session.add(row)
    row.funds = list(dict.fromkeys(criteria.funds))
    row.areas = list(dict.fromkeys(criteria.areas))
    row.authorities = list(dict.fromkeys(criteria.authorities))
    row.regions = list(criteria.regions)
    row.call_identifier = criteria.call_identifier.strip() or None if criteria.call_identifier else None
    session.commit()
