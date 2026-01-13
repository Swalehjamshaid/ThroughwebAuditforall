# fftech_website_audit_saas/app/email_utils.py

import os
import requests

UI_BRAND_NAME = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL")

SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"


def _build_verify_link(token: str) -> str:
    return f"{BASE_URL}/auth/verify?token={token}"


def send_verification_email(to_email: str, token: str) -> bool:
    """
    Sends verification email via SendGrid HTTP API.
    Fully compatible with Railway.
    """

    if not SENDGRID_API_KEY or not SENDGRID_FROM_EMAIL:
        print("[email] SendGrid not configured (missing API key or from email).")
        return False

    verify_link = _build_verify_link(token)

    payload = {
        "personalizations": [{
            "to": [{"email": to_email}],
            "subject": f"{UI_BRAND_NAME} – Verify your account"
        }],
        "from": {"email": SENDGRID_FROM_EMAIL},
        "content": [{
            "type": "text/html",
            "value": f"""
            <div style="font-family:Arial,sans-serif">
              <h2>{UI_BRAND_NAME}</h2>
              <p>Please verify your account by clicking the link below:</p>
              <p>
                <a href="{verify_link}"
                   style="background:#5B8CFF;color:white;padding:10px 16px;
                          text-decoration:none;border-radius:4px;">
                  Verify Account
                </a>
              </p>
              <p>If the button does not work, copy and paste this link:</p>
              <code>{verify_link}</code>
            </div>
            """
        }]
    }

    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            SENDGRID_API_URL,
            json=payload,
            headers=headers,
            timeout=10
        )

        if response.status_code in (200, 202):
            print(f"[email] Verification email sent to {to_email}")
            return True
        else:
            print(f"[email] SendGrid failed: {response.status_code} {response.text}")
            return False

    except Exception as e:
        print(f"[email] SendGrid exception: {e}")
        return False
