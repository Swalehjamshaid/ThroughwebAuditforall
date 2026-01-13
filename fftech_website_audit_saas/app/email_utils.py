
# app/email_utils.py
from __future__ import annotations

import os
import logging
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

# ------------------------------------------------------------------------------
# Environment-driven configuration
# ------------------------------------------------------------------------------
UI_BRAND_NAME: str = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")

SMTP_HOST: Optional[str] = os.getenv("SMTP_HOST", None)
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: Optional[str] = os.getenv("SMTP_USER", None)
SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD", None)

MAGIC_EMAIL_ENABLED: bool = os.getenv("MAGIC_EMAIL_ENABLED", "true").lower() == "true"

SMTP_TIMEOUT_SEC: float = float(os.getenv("SMTP_TIMEOUT_SEC", "6.0"))
SMTP_MAX_RETRIES: int = int(os.getenv("SMTP_MAX_RETRIES", "2"))  # total attempts = 1 + retries
SMTP_BACKOFF_BASE_SEC: float = float(os.getenv("SMTP_BACKOFF_BASE_SEC", "1.0"))

logger = logging.getLogger("fftech.app.email")

# ------------------------------------------------------------------------------
# Core SMTP sender (HTML)
# ------------------------------------------------------------------------------
def _smtp_send_html(to_email: str, subject: str, html_body: str) -> bool:
    """
    Send an HTML email with timeouts and bounded retries.
    Respects MAGIC_EMAIL_ENABLED. Returns True on success, False otherwise.
    """
    if not MAGIC_EMAIL_ENABLED:
        logger.warning("Email disabled by config (MAGIC_EMAIL_ENABLED=false); skipping send to %s", to_email)
        return False

    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        logger.warning("SMTP not configured; skip send to %s (SMTP_HOST/SMTP_USER/SMTP_PASSWORD required)", to_email)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER or ""
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    delay = SMTP_BACKOFF_BASE_SEC
    attempts = SMTP_MAX_RETRIES + 1  # initial attempt + retries
    for attempt in range(1, attempts + 1):
        try:
            logger.info(
                "SMTP: connecting %s:%s as %s (attempt %d/%d, timeout=%.1fs)",
                SMTP_HOST, SMTP_PORT, SMTP_USER, attempt, attempts, SMTP_TIMEOUT_SEC
            )
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SEC) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(SMTP_USER, SMTP_PASSWORD)  # type: ignore[arg-type]
                server.sendmail(SMTP_USER, [to_email], msg.as_string())  # type: ignore[arg-type]
            logger.info("SMTP: sent email to %s", to_email)
            return True
        except (smtplib.SMTPException, OSError) as e:
            # Covers DNS issues, "Network is unreachable", auth errors, etc.
            logger.warning("SMTP send failure to %s: %s", to_email, e)
            if attempt < attempts:
                time.sleep(delay)
                delay *= 2
                continue
            return False
        except Exception as e:
            logger.warning("Unexpected SMTP error to %s: %s", to_email, e)
            return False

# ------------------------------------------------------------------------------
# Public helpers used by main.py
# ------------------------------------------------------------------------------
def send_verification_email(to_email: str, token: str) -> bool:
    """
    Sends the account verification link.
    """
    link = f"{BASE_URL.rstrip('/')}/auth/verify?token={token}"
    html_body = f"""
    <h3>{UI_BRAND_NAME} — Verify your email</h3>
    <p>Hello!</p>
    <p>Click the link below to verify your account:</p>
    <p>{link}{link}</a></p>
    <p>This link will expire shortly. If you didn't request it, ignore this message.</p>
    """
    return _smtp_send_html(to_email, f"{UI_BRAND_NAME} — Verify your email", html_body)


def send_magic_login_email(to_email: str, token: str) -> bool:
    """
    Sends a magic login link for passwordless sign-in.
    """
    link = f"{BASE_URL.rstrip('/')}/auth/magic?token={token}"
    html_body = f"""
    <h3>{UI_BRAND_NAME} — Magic Login</h3>
    <p>Hello!</p>
    <p>Click the secure link below to log in:</p>
    <p>{link}{link}</a></p>
    <p>This link will expire shortly. If you didn't request it, ignore this message.</p>
    """
    return _smtp_send_html(to_email, f"{UI_BRAND_NAME} — Magic Login Link", html_body)


def send_daily_report_email(to_email: str, html_body: str) -> bool:
    """
    Sends the daily report email (HTML body prepared by caller).
    """
    return _smtp_send_html(to_email, f"{UI_BRAND_NAME} – Daily Website Audit Summary", html_body)
