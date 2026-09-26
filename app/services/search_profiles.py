"""MVP:n yhteinen hakusanaprofiili olemassa olevassa SearchProfile-taulussa."""

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluators.relevance import normalize_keywords
from app.models import SearchProfile

RELEVANCE_PROFILE_NAME = "HankeVAHTI: relevanssi"


@dataclass(frozen=True)
class KeywordSettings:
    keywords: tuple[str, ...] = ()
    excluded_keywords: tuple[str, ...] = ()


def get_relevance_profile(session: Session) -> SearchProfile | None:
    return session.scalar(
        select(SearchProfile)
        .where(SearchProfile.name == RELEVANCE_PROFILE_NAME)
        .order_by(SearchProfile.id)
        .limit(1)
    )


def get_keyword_settings(session: Session) -> KeywordSettings:
    profile = get_relevance_profile(session)
    if profile is None:
        return KeywordSettings()
    return KeywordSettings(tuple(profile.keywords), tuple(profile.excluded_keywords))


def save_keyword_settings(
    session: Session, keywords: Iterable[str], excluded_keywords: Iterable[str],
) -> KeywordSettings:
    settings = KeywordSettings(normalize_keywords(keywords), normalize_keywords(excluded_keywords))
    try:
        profile = get_relevance_profile(session)
        if profile is None:
            profile = SearchProfile(name=RELEVANCE_PROFILE_NAME)
            session.add(profile)
        profile.keywords = list(settings.keywords)
        profile.excluded_keywords = list(settings.excluded_keywords)
        profile.active = True
        session.commit()
    except Exception:
        session.rollback()
        raise
    return settings
