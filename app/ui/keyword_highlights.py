"""Ulkoisen kuvaustekstin turvallinen hakusanakorostus."""

from collections.abc import Iterable
from html import escape

from app.evaluators.relevance import keyword_spans


def highlight_keywords(text: str, keywords: Iterable[str]) -> str:
    parts = []
    previous = 0
    for start, end in keyword_spans(text, keywords):
        parts.append(escape(text[previous:start]))
        parts.append(f"<strong>{escape(text[start:end])}</strong>")
        previous = end
    parts.append(escape(text[previous:]))
    return "".join(parts)
