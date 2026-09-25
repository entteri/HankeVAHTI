"""Ennustettava hakusanapisteytys ilman verkkopalveluja tai kielimallia."""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

KEYWORD_POINTS = 20
EXCLUSION_PENALTY = 20
RELEVANCE_THRESHOLDS = (
    (80, "Hyvin relevantti"),
    (60, "Mahdollisesti relevantti"),
    (30, "Tarkistettava"),
    (0, "Todennäköisesti ei relevantti"),
)


def normalize_keywords(values: Iterable[str]) -> tuple[str, ...]:
    """Siisti välilyönnit ja Unicode; laske sama sana vain kerran."""
    result = []
    seen = set()
    for value in values:
        word = " ".join(unicodedata.normalize("NFC", value).split())
        key = word.casefold()
        if word and key not in seen:
            result.append(word)
            seen.add(key)
    return tuple(result)


def relevance_label(score: int | None) -> str:
    if score is None:
        return "Ei vielä pisteytetty"
    for minimum, label in RELEVANCE_THRESHOLDS:
        if score >= minimum:
            return label
    return RELEVANCE_THRESHOLDS[-1][1]


@dataclass(frozen=True)
class RelevanceResult:
    score: int
    matched_keywords: tuple[str, ...]
    matched_excluded_keywords: tuple[str, ...]
    summary: str


def evaluate_relevance(
    text_fields: Iterable[str | None],
    keywords: Iterable[str],
    excluded_keywords: Iterable[str],
) -> RelevanceResult:
    """Täsmää kokonaisia sanoja/ilmauksia; sama osuma ei kerrytä pisteitä."""
    texts = [" ".join(unicodedata.normalize("NFC", text).casefold().split())
             for text in text_fields if text]

    def matches(words: Iterable[str]) -> tuple[str, ...]:
        return tuple(
            word for word in normalize_keywords(words)
            if any(re.search(r"(?<!\w)" + re.escape(word.casefold()) + r"(?!\w)", text)
                   for text in texts)
        )

    matched = matches(keywords)
    excluded = matches(excluded_keywords)
    positive = min(100, len(matched) * KEYWORD_POINTS)
    penalty = len(excluded) * EXCLUSION_PENALTY
    score = max(0, positive - penalty)
    summary = (
        f"Osuvat hakusanat ({len(matched)}): {', '.join(matched) or 'ei osumia'}.\n"
        f"Poissulkevat osumat ({len(excluded)}): {', '.join(excluded) or 'ei osumia'}.\n"
        f"Kukin eri hakusana antaa {KEYWORD_POINTS} pistettä (yhteensä enintään 100). "
        f"Kukin eri poissulkusana vähentää {EXCLUSION_PENALTY} pistettä. "
        f"Laskenta: {positive} − {penalty}, rajattu välille 0–100 = {score}.\n"
        "Vertailu: nimi, kuvaus, rahasto ja kategoria. "
        "Kokonaiset sanat ja ilmaukset, kirjainkoosta riippumatta. "
        "Tulos on suositus; osallistumispäätös kuuluu käyttäjälle."
    )
    return RelevanceResult(score, matched, excluded, summary)
