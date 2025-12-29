
# fftech_audit/auth_email.py
import os
import time
import hmac
import hashlib
import base64
import smtplib
import json
from email.message import EmailMessage
from typing import Dict, Any

# Environment
SECRET = os.getenv("SECRET_KEY", "dev-secret-change-me")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
FROM_EMAIL = os.getenv("FROM_EMAIL", "no-reply@fftech.ai")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")


# --- HMAC signer over the base64 payload ---
def _sign(data: bytes) -> str:
    sig = hmac.new(SECRET.encode("utf-8"), data, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode("utf-8")


# --- Token generation using JSON for safe parsing ---
def generate_token(payload: Dict[str, Any], ttl_seconds: int = 3600) -> str:
    data = dict(payload)
    data["exp"] = int(time.time()) + ttl_seconds
    # JSON string → base64
    raw_json = json.dumps(data, separators=(",", ":"))
    raw_b64 = base64.urlsafe_b64encode(raw_json.encode("utf-8"))
    sig = _sign(raw_b64)
    return raw_b64.decode("utf-8") + "." + sig


def _decode_token(token: str) -> Dict[str, Any]:
    if "." not in token:
        raise ValueError("Invalid token format")
    raw_b64, sig = token.split(".", 1)
    raw = raw_b64.encode("utf-8")
    if _sign(raw) != sig:
        raise ValueError("Invalid signature")
    payload_str = base64.urlsafe_b64decode(raw).decode("utf-8")
    data = json.loads(payload_str)  # safe, exact JSON
    return data


def verify_session_token(token: str) -> Dict[str, Any]:
    data = _decode_token(token)
    if int(data.get("exp", 0)) < int(time.time()):
        raise ValueError("Token expired")
    return data


def verify_magic_or_verify_link(token: str) -> str:
    data = verify_session_token(token)
    email = data.get("email")
    if not email:
        raise ValueError("Email missing in token")
    return email


# --- Email sending helpers ---
def send_verification_link(email: str):
    token = generate_token({"email": email, "purpose": "verify"}, ttl_seconds=3600)
    verify_url = f"{BASE_URL}/auth/verify-link?token={token}"
    subject = "Your FF Tech AI secure login link"
    body = f"Click to complete registration: {verify_url}\n\nThis link expires in 60 minutes."
    _send_email(email, subject, body)


def send_email_with_pdf(to_email: str, subject: str, body: str, pdf_bytes: bytes):
    msg = EmailMessage()
    msg["From"] = FROM_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename="FFTech_Audit.pdf",
    )
    _deliver(msg)


def _send_email(to_email: str, subject: str, body: str):
    msg = EmailMessage()
    msg["From"] = FROM_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    _deliver(msg)


def _deliver(msg: EmailMessage):
    # If SMTP isn’t configured, log to stdout (so it won’t crash your container)
    if not SMTP_HOST:
        print("[EMAIL] SMTP not configured; printing email instead:")
        print(msg)
        return
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        if SMTP_USER and SMTP_PASS:
            server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
        print("[EMAIL] Sent to", msg["To"])
``
