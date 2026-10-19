from __future__ import annotations

import smtplib
from email.message import EmailMessage

from nba.config import Settings


def send_email(settings: Settings, subject: str, body: str) -> str:
    """Send an alert email via SMTP (Gmail app password recommended). Returns the To address."""
    missing = [
        name
        for name, val in [
            ("SMTP_USER", settings.smtp_user),
            ("SMTP_PASSWORD", settings.smtp_password),
            ("EMAIL_TO", settings.email_to),
        ]
        if not val
    ]
    if missing:
        raise RuntimeError(
            "Email is not configured. Missing: " + ", ".join(missing)
            + ". For Gmail, create an App Password at "
            "https://myaccount.google.com/apppasswords"
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.email_from or settings.smtp_user
    msg["To"] = settings.email_to
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)

    return settings.email_to
