"""SMTP notification transport using only Python's standard library."""

from __future__ import annotations

import os
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.policy import SMTP as SMTP_POLICY

from app.services.notifications import NotificationEmail, NotificationSendError


class SMTPConfigurationError(ValueError):
    """SMTP settings are missing or invalid."""


@dataclass(frozen=True)
class SMTPSettings:
    host: str
    port: int
    security: str
    username: str
    password: str
    from_address: str

    @classmethod
    def from_environment(cls) -> "SMTPSettings":
        required = {
            "SMTP_HOST": os.getenv("SMTP_HOST", "").strip(),
            "SMTP_PORT": os.getenv("SMTP_PORT", "").strip(),
            "SMTP_SECURITY": os.getenv("SMTP_SECURITY", "").strip().lower(),
            "SMTP_USERNAME": os.getenv("SMTP_USERNAME", "").strip(),
            "SMTP_PASSWORD": os.getenv("SMTP_PASSWORD", ""),
            "SMTP_FROM_ADDRESS": os.getenv("SMTP_FROM_ADDRESS", "").strip(),
            "NOTIFICATION_EMAIL_TO": os.getenv("NOTIFICATION_EMAIL_TO", "").strip(),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise SMTPConfigurationError(
                "Puuttuvat sähköpostiasetukset: " + ", ".join(missing)
            )
        try:
            port = int(required["SMTP_PORT"])
        except ValueError as exc:
            raise SMTPConfigurationError("SMTP_PORT-arvon pitää olla kokonaisluku.") from exc
        if not 1 <= port <= 65535:
            raise SMTPConfigurationError("SMTP_PORT-arvon pitää olla välillä 1–65535.")
        security = required["SMTP_SECURITY"]
        if security not in {"starttls", "ssl"}:
            raise SMTPConfigurationError("SMTP_SECURITY-arvon pitää olla starttls tai ssl.")
        return cls(
            host=required["SMTP_HOST"],
            port=port,
            security=security,
            username=required["SMTP_USERNAME"],
            password=required["SMTP_PASSWORD"],
            from_address=required["SMTP_FROM_ADDRESS"],
        )


class SMTPNotificationSender:
    def __init__(self, settings: SMTPSettings | None = None, *, timeout: float = 30.0) -> None:
        self.settings = settings or SMTPSettings.from_environment()
        self.timeout = timeout

    def send(self, message: NotificationEmail) -> None:
        if not message.recipient:
            raise NotificationSendError(
                "NOTIFICATION_EMAIL_TO-asetus puuttuu.", outcome_unknown=False,
            )

        try:
            email = EmailMessage()
            email["From"] = self.settings.from_address
            email["To"] = message.recipient
            email["Subject"] = message.subject
            email.set_content(message.body)
            payload = email.as_bytes(policy=SMTP_POLICY)
            payload = re.sub(br"(?m)^\.", b"..", payload)
            if not payload.endswith(b"\r\n"):
                payload += b"\r\n"
        except (TypeError, ValueError) as exc:
            raise NotificationSendError(
                f"Sähköpostiviestin otsake tai sisältö ei kelpaa: {exc}",
                outcome_unknown=False,
            ) from exc

        smtp: smtplib.SMTP | None = None
        data_started = False
        try:
            if self.settings.security == "ssl":
                smtp = smtplib.SMTP_SSL(
                    self.settings.host,
                    self.settings.port,
                    timeout=self.timeout,
                    context=ssl.create_default_context(),
                )
            else:
                smtp = smtplib.SMTP(
                    self.settings.host,
                    self.settings.port,
                    timeout=self.timeout,
                )
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()

            smtp.login(self.settings.username, self.settings.password)
            code, response = smtp.mail(self.settings.from_address)
            if code != 250:
                raise NotificationSendError(
                    f"SMTP-palvelin hylkäsi lähettäjän ({code}): {response!r}",
                    outcome_unknown=False,
                )
            code, response = smtp.rcpt(message.recipient)
            if code not in (250, 251):
                raise NotificationSendError(
                    f"SMTP-palvelin hylkäsi vastaanottajan ({code}): {response!r}",
                    outcome_unknown=False,
                )
            code, response = smtp.docmd("DATA")
            if code != 354:
                raise NotificationSendError(
                    f"SMTP-palvelin ei hyväksynyt viestin sisältöä ({code}): {response!r}",
                    outcome_unknown=False,
                )

            data_started = True
            smtp.send(payload + b".\r\n")
            code, response = smtp.getreply()
            data_started = False
            if code != 250:
                raise NotificationSendError(
                    f"SMTP-palvelin ei hyväksynyt viestiä ({code}): {response!r}",
                    outcome_unknown=False,
                )
        except NotificationSendError:
            raise
        except Exception as exc:
            raise NotificationSendError(
                f"SMTP-lähetys epäonnistui: {exc}",
                outcome_unknown=data_started,
            ) from exc
        finally:
            if smtp is not None:
                try:
                    smtp.quit()
                except Exception:
                    try:
                        smtp.close()
                    except Exception:
                        pass
