
"""
Email utilities (Resend) for FFTech Audit SaaS.

Functions:
- build_verification_link(base_url, token)
- send_verification_email(to_email, brand, verify_link)
- send_report_email(to_email, brand, pdf_path, website_url, score, grade)

Configuration via ENV:
- RESEND_API_KEY
- RESEND_FROM_EMAIL
"""

import os
import json
import base64
from typing import Optional, Dict, Any

import requests


RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "")


def _assert_config():
    if not RESEND_API_KEY or not RESEND_FROM_EMAIL:
        raise RuntimeError("Resend not configured: set RESEND_API_KEY and RESEND_FROM_EMAIL env variables.")


def build_verification_link(base_url: str, token: str) -> str:
    base_url = (base_url or "").rstrip("/")
    return f"{base_url}/auth/verify?token={token}"


def _send_resend_email(payload: Dict[str, Any]) -> None:
    _assert_config()
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, headers=headers, data=json.dumps(payload))
    if not (200 <= resp.status_code < 300):
        raise RuntimeError(f"Resend error: {resp.status_code} {resp.text}")


def send_verification_email(to_email: str, brand: str, verify_link: str) -> None:
    """
    Sends a simple verification email with a link.
    """
    payload = {
        "from": RESEND_FROM_EMAIL,
        "to": [to_email],
        "subject": f"{brand} — Verify your email",
        "text": (
            f"Welcome to {brand}!\n\n"
            f"Please verify your email by visiting:\n{verify_link}\n\n"
            "If you did not sign up, you can ignore this email."
        ),
    }
    _send_resend_email(payload)


def send_report_email(
    to_email: str,
    brand: str,
    pdf_path: str,
    website_url: str,
    score: int,
    grade: str,
    subject: Optional[str] = None,
    body: Optional[str] = None,
) -> None:
    """
    Sends a report email with the audit PDF attached (base64).
    """
    _assert_config()

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    with open(pdf_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "from": RESEND_FROM_EMAIL,
        "to": [to_email],
        "subject": subject or f"{brand} — Your Certified Website Audit Report",
        "text": body or (
            f"Your latest audit for {website_url} is ready.\n"
            f"Health Score: {score}\nGrade: {grade}\n\n"
            "The certified PDF is attached. Thank you for using our service."
        ),
        "attachments": [
            {"filename": os.path.basename(pdf_path), "content": b64}
        ],
    }
    _send_resend_email(payload)
``
