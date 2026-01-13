
# app/email_utils.py
from __future__ import annotations

import os
import logging
import smtplib
import time
import json
from typing import Optional

import socket
import ssl
import http.client
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ------------------------------------------------------------------------------
# Environment-driven configuration
# ------------------------------------------------------------------------------
UI_BRAND_NAME: str = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")

# --- SendGrid HTTP API (primary) ---
SENDGRID_API_KEY: Optional[str] = os.getenv("SENDGRID_API_KEY", None)
SENDGRID_FROM_EMAIL: Optional[str] = os.getenv("SENDGRID_FROM_EMAIL", None)

# --- SMTP (fallback) ---
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
# SendGrid sender (HTTP API)
# ------------------------------------------------------------------------------
def _send_via_sendgrid(to_email: str, subject: str, html_body: str) -> bool:
    """
    Send an HTML email using SendGrid HTTP API (primary path).
    Returns True on success, False otherwise.
    """
    if not MAGIC_EMAIL_ENABLED:
        logger.warning("Email disabled (MAGIC_EMAIL_ENABLED=false); skipping SendGrid send to %s", to_email)
        return False

    if not (SENDGRID_API_KEY and SENDGRID_FROM_EMAIL):
        logger.debug("SendGrid not configured; missing SENDGRID_API_KEY or SENDGRID_FROM_EMAIL.")
        return False

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": SENDGRID_FROM_EMAIL},
        "subject": subject,
        "content": [{"type": "text/html", "value": html_body}],
    }
    body = json.dumps(payload)

    delay = SMTP_BACKOFF_BASE_SEC
    attempts = SMTP_MAX_RETRIES + 1
    for attempt in range(1, attempts + 1):
        try:
            logger.info("SendGrid: POST /v3/mail/send (attempt %d/%d)", attempt, attempts)
            # Build HTTPS connection with timeout
            context = ssl.create_default_context()
            conn = http.client.HTTPSConnection("api.sendgrid.com", timeout=SMTP_TIMEOUT_SEC, context=context)
            headers = {
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            }
            conn.request("POST", "/v3/mail/send", body=body, headers=headers)
            resp = conn.getresponse()
            status = resp.status
            resp.read()  # drain
            conn.close()

            # SendGrid returns 202 for success
            if 200 <= status < 300:
                logger.info("SendGrid: sent email to %s (status=%d)", to_email, status)
                return True

            logger.warning("SendGrid send failure to %s: HTTP %d", to_email, status)
            if attempt < attempts:
                time.sleep(delay)
                delay *= 2
                continue
            return False
        except (socket.timeout, ConnectionError, ssl.SSLError, OSError, http.client.HTTPException) as e:
            logger.warning("SendGrid network error to %s: %s", to_email, e)
            if attempt < attempts:
                time.sleep(delay)
                delay *= 2
                continue
            return False
        except Exception as e:
            logger.warning("SendGrid unexpected error to %s: %s", to_email, e)
            return False


# ------------------------------------------------------------------------------
# SMTP sender (fallback)
# ------------------------------------------------------------------------------
def _smtp_send_html(to_email: str, subject: str, html_body: str) -> bool:
    """
    Send an HTML email via SMTP with timeouts and bounded retries.
    Returns True on success, False otherwise.
    """
    if not MAGIC_EMAIL_ENABLED:
        logger.warning("Email disabled (MAGIC_EMAIL_ENABLED=false); skipping SMTP send to %s", to_email)
        return False

    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        logger.debug("SMTP not configured; missing SMTP_HOST/SMTP_USER/SMTP_PASSWORD.")
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
        except (smtplib.SMTPException, OSError, socket.timeout) as e:
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
# Unified public helper (SendGrid primary, SMTP fallback)
# ------------------------------------------------------------------------------
def _send_email_html(to_email: str, subject: str, html_body: str) -> bool:
    """
    Try SendGrid first (if configured), then SMTP fallback.
    """
    # Primary: SendGrid
    if SENDGRID_API_KEY and SENDGRID_FROM_EMAIL:
        if _send_via_sendgrid(to_email, subject, html_body):
            return True

    # Fallback: SMTP
    if SMTP_HOST and SMTP_USER and SMTP_PASSWORD:
        return _smtp_send_html(to_email, subject, html_body)

    logger.warning("No email transport available; email to %s dropped.", to_email)
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
    <p>This link will expire shortly. If you didn't request it, you can safely ignore this message.</p>
    """
    return _send_email_html(to_email, f"{UI_BRAND_NAME} — Verify your email", html_body)


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
    <p>This link will expire shortly. If you didn't request it, you can safely ignore this message.</p>
    """
    return _send_email_html(to_email, f"{UI_BRAND_NAME} — Magic Login Link", html_body)


def send_daily_report_email(to_email: str, html_body: str) -> bool:
    """
    Sends the daily report email (HTML body prepared by caller).
    """
    return _send_email_html(to_email, f"{UI_BRAND_NAME} – Daily Website Audit Summary", html_body)
