"""Haeavustuksia.fi:n hakuehtojen tallennus."""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import HaeavustuksiaSearchCriteria

GRANT_TYPE_LABELS = {
    "Hankeavustus": "Hankeavustus",
    "Apuraha": "Apuraha",
    "Yleisavustus": "Yleisavustus",
    "Investointiavustus": "Investointiavustus",
    "MuuErityisavustus": "Muu erityisavustus",
}


@dataclass(frozen=True)
class HaeavustuksiaCriteria:
    grant_types: list[str] = field(default_factory=list)
    show_future: bool = True
    show_ongoing: bool = True
    authorities: list[str] = field(default_factory=list)


def get_haeavustuksia_criteria(session: Session) -> HaeavustuksiaCriteria:
    row = session.get(HaeavustuksiaSearchCriteria, 1)
    if row is None:
        return HaeavustuksiaCriteria()
    return HaeavustuksiaCriteria(
        grant_types=list(row.grant_types),
        show_future=row.show_future,
        show_ongoing=row.show_ongoing,
        authorities=list(row.authorities),
    )


def save_haeavustuksia_criteria(session: Session, criteria: HaeavustuksiaCriteria) -> None:
    if any(grant_type not in GRANT_TYPE_LABELS for grant_type in criteria.grant_types):
        raise ValueError("Tuntematon avustuslaji")
    row = session.get(HaeavustuksiaSearchCriteria, 1)
    if row is None:
        row = HaeavustuksiaSearchCriteria(id=1)
        session.add(row)
    row.grant_types = list(dict.fromkeys(criteria.grant_types))
    row.show_future = criteria.show_future
    row.show_ongoing = criteria.show_ongoing
    row.authorities = list(dict.fromkeys(criteria.authorities))
    session.commit()
