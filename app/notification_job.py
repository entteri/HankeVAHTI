"""One-shot notification job for Windows Task Scheduler."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.core import config
from app.db.session import SessionLocal
from app.services.notifications import run_notification
from app.services.smtp_sender import SMTPNotificationSender

HELSINKI = ZoneInfo("Europe/Helsinki")


def scheduled_date(now: datetime | None = None) -> date:
    """Return the latest scheduled occurrence on or before the current Helsinki date."""
    local_now = (now or datetime.now(HELSINKI)).astimezone(HELSINKI)
    return local_now.date().replace(day=15 if local_now.day >= 15 else 1)


def next_run_at(current_run_date: date, run_time: str | None = None) -> datetime:
    if current_run_date.day == 1:
        next_date = current_run_date.replace(day=15)
    elif current_run_date.day == 15:
        year = current_run_date.year + (current_run_date.month == 12)
        month = 1 if current_run_date.month == 12 else current_run_date.month + 1
        next_date = date(year, month, 1)
    else:
        raise ValueError("Ajastetun hakupäivän pitää olla kuukauden 1. tai 15. päivä.")
    try:
        scheduled_time = time.fromisoformat(run_time or config.NOTIFICATION_RUN_TIME)
    except ValueError as exc:
        raise ValueError("NOTIFICATION_RUN_TIME-arvon pitää olla muodossa HH:MM.") from exc
    if scheduled_time.second or scheduled_time.microsecond:
        raise ValueError("NOTIFICATION_RUN_TIME-arvon pitää olla muodossa HH:MM.")
    return datetime.combine(next_date, scheduled_time, tzinfo=HELSINKI)


def _parse_scheduled_date(value: str) -> date:
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Päivämäärän pitää olla muodossa YYYY-MM-DD.") from exc
    if result.day not in (1, 15):
        raise argparse.ArgumentTypeError("Päivämäärän pitää olla kuukauden 1. tai 15. päivä.")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Suorita HankeVAHTI-ilmoitushaku kerran.")
    parser.add_argument(
        "--scheduled-date",
        type=_parse_scheduled_date,
        help="Ajastetun hakukerran päivä (YYYY-MM-DD); käytä samaa päivää uusintayrityksessä.",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Yritä samaa ajoa uudelleen vain, jos edellinen lähetys epäonnistui varmasti.",
    )
    args = parser.parse_args(argv)

    try:
        sender = SMTPNotificationSender()
        run_date = args.scheduled_date or scheduled_date()
        planned_next_run = next_run_at(run_date)
        run_key = f"scheduled:{run_date.isoformat()}"
        with SessionLocal() as session:
            result = run_notification(
                session,
                sender,
                run_key=run_key,
                next_run_at=planned_next_run,
                retry_failed=args.retry_failed,
            )
    except Exception as exc:
        print(f"HankeVAHTI-ilmoitusajo epäonnistui: {exc}", file=sys.stderr)
        return 1

    print(f"HankeVAHTI-ilmoitusajo {result.run_key}: {result.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
