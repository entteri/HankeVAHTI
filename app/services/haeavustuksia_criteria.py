"""Haeavustuksia.fi:n hakuehtojen tallennus."""

from dataclasses import dataclass

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
    grant_type: str | None = None
    show_future: bool = True
    show_ongoing: bool = True
    authority: str | None = None


def get_haeavustuksia_criteria(session: Session) -> HaeavustuksiaCriteria:
    row = session.get(HaeavustuksiaSearchCriteria, 1)
    if row is None:
        return HaeavustuksiaCriteria()
    return HaeavustuksiaCriteria(
        grant_type=row.grant_type,
        show_future=row.show_future,
        show_ongoing=row.show_ongoing,
        authority=row.authority,
    )


def save_haeavustuksia_criteria(session: Session, criteria: HaeavustuksiaCriteria) -> None:
    if criteria.grant_type is not None and criteria.grant_type not in GRANT_TYPE_LABELS:
        raise ValueError("Tuntematon avustuslaji")
    row = session.get(HaeavustuksiaSearchCriteria, 1)
    if row is None:
        row = HaeavustuksiaSearchCriteria(id=1)
        session.add(row)
    row.grant_type = criteria.grant_type
    row.show_future = criteria.show_future
    row.show_ongoing = criteria.show_ongoing
    row.authority = criteria.authority
    session.commit()
