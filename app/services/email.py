from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.core.config import settings


class EmailDeliveryError(RuntimeError):
    pass


def member_login_email_delivery_status() -> dict[str, str | bool]:
    if settings.smtp_host and settings.email_from:
        return {
            "configured": True,
            "label": "SMTP",
            "detail": f"Sending member login links and codes from {settings.email_from}.",
        }
    return {
        "configured": False,
        "label": "Logs only",
        "detail": "Member login links and codes are printed to web logs.",
    }


def send_member_login_code(*, to_email: str, code: str, magic_link: str) -> None:
    if not settings.smtp_host or not settings.email_from:
        print(f"Trophy Case member login code for {to_email}: {code}")
        print(f"Trophy Case member login link for {to_email}: {magic_link}")
        return

    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to_email
    message["Subject"] = "Your Trophy Case login link"
    message.set_content(
        "Use this Trophy Case login link within 15 minutes:\n\n"
        f"{magic_link}\n\n"
        "Or enter this login code:\n\n"
        f"{code}\n\n"
        "If you did not request this code, you can ignore this email.\n"
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
            if settings.smtp_use_tls:
                client.starttls()
            if settings.smtp_username and settings.smtp_password:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError("Member login email could not be sent.") from exc
