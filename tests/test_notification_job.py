from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app import notification_job


def test_scheduled_date_uses_latest_monthly_occurrence_in_helsinki():
    helsinki = ZoneInfo("Europe/Helsinki")

    assert notification_job.scheduled_date(datetime(2027, 3, 4, 10, tzinfo=helsinki)) == date(2027, 3, 1)
    assert notification_job.scheduled_date(datetime(2027, 3, 15, 10, tzinfo=helsinki)) == date(2027, 3, 15)
    assert notification_job.scheduled_date(datetime(2027, 4, 2, 10, tzinfo=helsinki)) == date(2027, 4, 1)


def test_next_run_at_and_run_date_validation(monkeypatch):
    monkeypatch.setattr(notification_job.config, "NOTIFICATION_RUN_TIME", "08:30")

    next_at = notification_job.next_run_at(date(2027, 12, 15))
    assert next_at.isoformat() == "2028-01-01T08:30:00+02:00"
    with pytest.raises(ValueError, match="1. tai 15."):
        notification_job.next_run_at(date(2027, 12, 2))


def test_cli_passes_stable_run_key_and_failed_retry_flag(monkeypatch, capsys):
    calls = []

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeSender:
        def __init__(self):
            pass

    class FakeResult:
        run_key = "scheduled:2027-03-15"
        status = "SENT"

    monkeypatch.setattr(notification_job, "SMTPNotificationSender", FakeSender)
    monkeypatch.setattr(notification_job, "SessionLocal", FakeSession)

    def run_notification(session, sender, **kwargs):
        calls.append((session, sender, kwargs))
        return FakeResult()

    monkeypatch.setattr(notification_job, "run_notification", run_notification)

    exit_code = notification_job.main([
        "--scheduled-date", "2027-03-15", "--retry-failed",
    ])

    assert exit_code == 0
    assert calls[0][2]["run_key"] == "scheduled:2027-03-15"
    assert calls[0][2]["retry_failed"] is True
    assert calls[0][2]["next_run_at"].isoformat() == "2027-04-01T09:00:00+03:00"
    assert "scheduled:2027-03-15: SENT" in capsys.readouterr().out


def test_cli_reports_smtp_configuration_error_without_running_job(monkeypatch, capsys):
    def fail_sender():
        raise ValueError("Puuttuvat sähköpostiasetukset: SMTP_HOST")

    monkeypatch.setattr(notification_job, "SMTPNotificationSender", fail_sender)
    monkeypatch.setattr(
        notification_job,
        "run_notification",
        lambda *args, **kwargs: pytest.fail("Ilmoitusajoa ei saa käynnistää ilman asetuksia"),
    )

    assert notification_job.main(["--scheduled-date", "2027-03-15"]) == 1
    assert "SMTP_HOST" in capsys.readouterr().err
