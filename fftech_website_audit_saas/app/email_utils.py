import os
import requests
import logging

logger = logging.getLogger("fftech.email")

UI_BRAND_NAME = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL")
SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"

def send_verification_email(to_email: str, token: str) -> bool:
    """Sends verification link via HTTP POST (Port 443) to SendGrid."""
    if not SENDGRID_API_KEY or not SENDGRID_FROM_EMAIL:
        logger.warning("SendGrid missing configuration.")
        return False

    verify_link = f"{BASE_URL.rstrip('/')}/auth/verify?token={token}"

    payload = {
        "personalizations": [{"to": [{"email": to_email}], "subject": f"Verify {UI_BRAND_NAME}"}],
        "from": {"email": SENDGRID_FROM_EMAIL},
        "content": [{"type": "text/html", "value": f"""
            <div style="font-family:sans-serif; padding:20px; border:1px solid #ddd;">
                <h2>{UI_BRAND_NAME}</h2>
                <p>Click below to verify your account:</p>
                <a href="{verify_link}" style="background:#5B8CFF; color:white; padding:10px 20px; text-decoration:none; border-radius:5px;">Verify Now</a>
                <p>Or copy this: {verify_link}</p>
            </div>
        """}]
    }

    headers = {"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"}

    try:
        resp = requests.post(SENDGRID_API_URL, json=payload, headers=headers, timeout=10)
        return resp.status_code in (200, 202)
    except Exception as e:
        logger.error(f"SendGrid Error: {e}")
        return False
