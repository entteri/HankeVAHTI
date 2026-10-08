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


def _keyword_pattern(word: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + re.escape(word.casefold()) + r"(?!\w)")


def keyword_spans(text: str, keywords: Iterable[str]) -> list[tuple[int, int]]:
    """Palauta osumat alkuperäisen tekstin indekseinä pisteytyksen säännöillä.

    Säilytä indeksikartta Unicode- ja välilyöntinormalisoinnissa sekä
    casefoldissa (esimerkiksi ß -> ss), jotta esityksen kirjoitusasu ei muutu.
    """
    clusters: list[tuple[str, int, int]] = []
    for index, char in enumerate(text):
        if clusters and (unicodedata.combining(char) or
                         unicodedata.normalize("NFC", clusters[-1][0] + char) !=
                         unicodedata.normalize("NFC", clusters[-1][0]) + unicodedata.normalize("NFC", char)):
            previous, start, _ = clusters[-1]
            clusters[-1] = (previous + char, start, index + 1)
        else:
            clusters.append((char, index, index + 1))
    normalized: list[str] = []
    offsets: list[tuple[int, int]] = []
    for cluster, start, end in clusters:
        for char in unicodedata.normalize("NFC", cluster).casefold():
            if char.isspace():
                if normalized and normalized[-1] == " ":
                    offsets[-1] = (offsets[-1][0], end)
                    continue
                char = " "
            normalized.append(char)
            offsets.append((start, end))
    searchable = "".join(normalized)
    spans = sorted(
        (offsets[match.start()][0], offsets[match.end() - 1][1])
        for word in normalize_keywords(keywords)
        for match in _keyword_pattern(word).finditer(searchable)
    )
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


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
            if any(_keyword_pattern(word).search(text)
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
