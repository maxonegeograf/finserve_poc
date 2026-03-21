"""Optional SMTP email (configure via .env). Uses only the standard library."""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from ssl import create_default_context

from dotenv import load_dotenv

load_dotenv()


def smtp_configured() -> bool:
    host = (os.getenv("SMTP_HOST") or "").strip()
    user = (os.getenv("SMTP_USER") or "").strip()
    pwd = (os.getenv("SMTP_PASSWORD") or os.getenv("SMTP_PASS") or "").strip()
    return bool(host and user and pwd)


def send_html_email(*, to_addr: str, subject: str, html_body: str, text_fallback: str | None = None) -> tuple[bool, str]:
    """Send email via SMTP. Returns (success, message for UI)."""
    to_addr = (to_addr or "").strip()
    if not to_addr or "@" not in to_addr:
        return False, "Please enter a valid email address."

    if not smtp_configured():
        return False, (
            "Email is not configured. Set SMTP_HOST, SMTP_USER, and SMTP_PASSWORD in your .env file "
            "(and optionally SMTP_PORT, SMTP_FROM, SMTP_USE_TLS)."
        )

    host = (os.getenv("SMTP_HOST") or "").strip()
    port = int((os.getenv("SMTP_PORT") or "587").strip() or "587")
    user = (os.getenv("SMTP_USER") or "").strip()
    password = (os.getenv("SMTP_PASSWORD") or os.getenv("SMTP_PASS") or "").strip()
    mail_from = (os.getenv("SMTP_FROM") or user).strip()
    use_tls = (os.getenv("SMTP_USE_TLS", "true").strip().lower() in ("1", "true", "yes"))

    plain = text_fallback or "Open this message in an HTML-capable client."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = to_addr
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if use_tls:
            context = create_default_context()
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.starttls(context=context)
                server.login(user, password)
                server.sendmail(mail_from, [to_addr], msg.as_string())
        else:
            with smtplib.SMTP_SSL(host, port, timeout=30, context=create_default_context()) as server:
                server.login(user, password)
                server.sendmail(mail_from, [to_addr], msg.as_string())
        return True, f"Message sent to {to_addr}."
    except OSError as exc:
        return False, f"Send failed: {exc}"
