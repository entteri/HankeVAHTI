"""Shared local-time display for UTC timestamps, including SQLite naive values."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def format_local_datetime(value: datetime | None) -> str:
    if value is None:
        return "Ei tiedossa"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo("Europe/Helsinki")).strftime("%d.%m.%Y klo %H:%M")
