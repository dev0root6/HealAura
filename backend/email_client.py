"""Minimal SMTP sender for the 'alert a friend' feature.

Gmail with an app password is the intended setup: set SMTP_USER to the Gmail
address and SMTP_PASSWORD to a 16-character app password (not the account
password). Sending runs in a worker thread so it does not block the event loop.
"""

import asyncio
import logging
import os
import smtplib
from typing import Optional
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "HealAura")


def configured() -> bool:
    """True when SMTP credentials are present, i.e. emails can actually go out."""
    return bool(SMTP_USER and SMTP_PASSWORD)


def _send_sync(to_email: str, subject: str, body: str, html: Optional[str] = None) -> None:
    if not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError(
            "SMTP is not configured. Set SMTP_USER and SMTP_PASSWORD in .env."
        )

    msg = EmailMessage()
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Reply-To"] = SMTP_USER
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


async def send_email(to_email: str, subject: str, body: str, html: Optional[str] = None) -> None:
    """Send one email (plain text, plus HTML if given), raising RuntimeError on failure."""
    try:
        await asyncio.to_thread(_send_sync, to_email, subject, body, html)
    except RuntimeError:
        raise
    except Exception as exc:  # smtplib raises a wide range of errors
        logger.warning("Email send failed: %s", exc)
        raise RuntimeError(f"Could not send the email: {exc}") from exc
