from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser

import pytest

from app.services.notifications import NotificationEmail, NotificationSendError, _message
from app.services.smtp_sender import (
    SMTPConfigurationError,
    SMTPNotificationSender,
    SMTPSettings,
)


def _set_smtp_env(monkeypatch):
    for key, value in {
        "SMTP_HOST": "mail.example.test",
        "SMTP_PORT": "587",
        "SMTP_SECURITY": "starttls",
        "SMTP_USERNAME": "user",
        "SMTP_PASSWORD": "secret",
        "SMTP_FROM_ADDRESS": "hankevahti@example.test",
        "NOTIFICATION_EMAIL_TO": "recipient@example.test",
    }.items():
        monkeypatch.setenv(key, value)


class FakeSMTP:
    instances = []
    rcpt_response = (250, b"accepted")
    data_response = (250, b"queued")
    fail_send = None

    def __init__(self, host, port, **kwargs):
        self.host = host
        self.port = port
        self.kwargs = kwargs
        self.calls = []
        self.payload = None
        self.__class__.instances.append(self)

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self, **kwargs):
        self.calls.append("starttls")

    def login(self, username, password):
        self.calls.append(("login", username, password))

    def mail(self, address):
        self.calls.append(("mail", address))
        return 250, b"sender accepted"

    def rcpt(self, address):
        self.calls.append(("rcpt", address))
        return self.rcpt_response

    def docmd(self, command):
        self.calls.append(("command", command))
        return 354, b"send content"

    def send(self, payload):
        self.payload = payload
        if self.fail_send:
            raise self.fail_send

    def getreply(self):
        return self.data_response

    def quit(self):
        self.calls.append("quit")

    def close(self):
        self.calls.append("close")


@pytest.fixture(autouse=True)
def reset_fake_smtp():
    FakeSMTP.instances = []
    FakeSMTP.rcpt_response = (250, b"accepted")
    FakeSMTP.data_response = (250, b"queued")
    FakeSMTP.fail_send = None


def test_missing_smtp_settings_are_reported(monkeypatch):
    for key in (
        "SMTP_HOST", "SMTP_PORT", "SMTP_SECURITY", "SMTP_USERNAME", "SMTP_PASSWORD",
        "SMTP_FROM_ADDRESS", "NOTIFICATION_EMAIL_TO",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(SMTPConfigurationError) as error:
        SMTPSettings.from_environment()

    assert "SMTP_HOST" in str(error.value)
    assert "NOTIFICATION_EMAIL_TO" in str(error.value)


def test_sender_sends_message_over_starttls(monkeypatch):
    _set_smtp_env(monkeypatch)
    monkeypatch.setattr("app.services.smtp_sender.smtplib.SMTP", FakeSMTP)
    sender = SMTPNotificationSender()
    message = NotificationEmail("recipient@example.test", "Testi", "Viestin sisältö")

    sender.send(message)

    fake = FakeSMTP.instances[0]
    parsed = BytesParser(policy=policy.default).parsebytes(fake.payload[:-3])
    assert fake.host == "mail.example.test"
    assert fake.port == 587
    assert "starttls" in fake.calls
    assert parsed["From"] == "hankevahti@example.test"
    assert parsed["To"] == "recipient@example.test"
    assert parsed["Subject"] == "Testi"
    assert parsed.get_content().strip() == "Viestin sisältö"


def test_sender_preserves_empty_result_message(monkeypatch):
    _set_smtp_env(monkeypatch)
    monkeypatch.setattr("app.services.smtp_sender.smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr("app.core.config.NOTIFICATION_EMAIL_TO", "recipient@example.test")
    empty_result_email = _message([], datetime(2027, 1, 15, 9, 0, tzinfo=timezone.utc))

    SMTPNotificationSender().send(empty_result_email)

    parsed = BytesParser(policy=policy.default).parsebytes(FakeSMTP.instances[0].payload[:-3])
    assert parsed["Subject"] == "Ei uusia potentiaalisia hankkeita"
    assert "eikä uusia sopiviksi arvioituja hankkeita löytynyt" in parsed.get_content()
    assert "Seuraava haku" in parsed.get_content()


def test_recipient_rejection_is_a_known_failure(monkeypatch):
    _set_smtp_env(monkeypatch)
    FakeSMTP.rcpt_response = (550, b"mailbox unavailable")
    monkeypatch.setattr("app.services.smtp_sender.smtplib.SMTP", FakeSMTP)

    with pytest.raises(NotificationSendError) as error:
        SMTPNotificationSender().send(NotificationEmail("recipient@example.test", "s", "b"))

    assert error.value.outcome_unknown is False
    assert FakeSMTP.instances[0].payload is None


def test_invalid_message_header_is_a_known_failure_before_connection(monkeypatch):
    _set_smtp_env(monkeypatch)
    monkeypatch.setattr("app.services.smtp_sender.smtplib.SMTP", FakeSMTP)

    with pytest.raises(NotificationSendError) as error:
        SMTPNotificationSender().send(
            NotificationEmail("recipient@example.test", "invalid\nsubject", "b")
        )

    assert error.value.outcome_unknown is False
    assert FakeSMTP.instances == []


def test_disconnect_after_data_started_is_uncertain(monkeypatch):
    _set_smtp_env(monkeypatch)
    FakeSMTP.fail_send = OSError("connection dropped")
    monkeypatch.setattr("app.services.smtp_sender.smtplib.SMTP", FakeSMTP)

    with pytest.raises(NotificationSendError) as error:
        SMTPNotificationSender().send(NotificationEmail("recipient@example.test", "s", "b"))

    assert error.value.outcome_unknown is True


def test_server_rejection_of_message_data_is_a_known_failure(monkeypatch):
    _set_smtp_env(monkeypatch)
    FakeSMTP.data_response = (554, b"message rejected")
    monkeypatch.setattr("app.services.smtp_sender.smtplib.SMTP", FakeSMTP)

    with pytest.raises(NotificationSendError) as error:
        SMTPNotificationSender().send(NotificationEmail("recipient@example.test", "s", "b"))

    assert error.value.outcome_unknown is False
