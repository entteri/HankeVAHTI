"""Find possible cross-source copies of the same funding call."""

import re
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FundingCall


@dataclass(frozen=True)
class DuplicateCall:
    id: int
    source: str
    title: str
    identifier: str
    source_url: str | None
    start_date: date | None
    end_date: date | None


@dataclass(frozen=True)
class DuplicateMatch:
    eura: DuplicateCall
    haeavustuksia: DuplicateCall
    reason: str


def _normalise(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold(), flags=re.UNICODE))


def _identifier(value: str | None) -> str:
    return "".join(re.findall(r"\w", (value or "").casefold(), flags=re.UNICODE))


def _close_dates(first: FundingCall, second: FundingCall) -> bool:
    compared = 0
    for field in ("application_start_date", "application_end_date"):
        left, right = getattr(first, field), getattr(second, field)
        if left and right:
            compared += 1
            if abs((left - right).days) > 7:
                return False
    return compared > 0


def _call_view(call: FundingCall) -> DuplicateCall:
    return DuplicateCall(
        id=call.id,
        source=call.source,
        title=call.title,
        identifier=call.call_identifier or call.source_id,
        source_url=call.source_url,
        start_date=call.application_start_date,
        end_date=call.application_end_date,
    )


def find_duplicate_matches(session: Session) -> list[DuplicateMatch]:
    """Return likely EURA/Haeavustuksia pairs; never merge or modify calls."""
    calls = session.scalars(
        select(FundingCall).where(FundingCall.source.in_(("EURA", "HAEAVUSTUKSIA")))
    ).all()
    eura = [call for call in calls if call.source == "EURA"]
    hae = [call for call in calls if call.source == "HAEAVUSTUKSIA"]
    matches = []
    for left in eura:
        left_title = _normalise(left.title)
        left_identifier = _identifier(left.call_identifier)
        for right in hae:
            right_identifier = _identifier(right.call_identifier)
            shared_identifier = (
                len(left_identifier) >= 6 and left_identifier == right_identifier
            )
            if shared_identifier:
                reason = "Sama hakutunnus molemmissa lähteissä."
            else:
                if not _close_dates(left, right):
                    continue
                right_title = _normalise(right.title)
                if min(len(left_title), len(right_title)) < 12:
                    continue
                if min(len(left_title), len(right_title)) / max(len(left_title), len(right_title)) < 0.75:
                    continue
                similarity = SequenceMatcher(None, left_title, right_title).ratio()
                if similarity < 0.86:
                    continue
                reason = "Samankaltainen nimi ja enintään 7 päivää eroavat tiedossa olevat hakuajat."
            matches.append(DuplicateMatch(_call_view(left), _call_view(right), reason))
    return sorted(matches, key=lambda match: (match.eura.title.casefold(), match.haeavustuksia.title.casefold()))
