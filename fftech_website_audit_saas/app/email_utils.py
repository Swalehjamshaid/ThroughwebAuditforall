# app/email_utils.py
import os
from resend import Resend

UI_BRAND_NAME = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip('/')

# Initialize Resend client (recommended)
resend_client = Resend(api_key=os.getenv("RESEND_API_KEY"))

def _build_verify_link(token: str) -> str:
    return f"{BASE_URL}/auth/verify?token={token}"

def _build_magic_link(token: str) -> str:
    return f"{BASE_URL}/auth/magic?token={token}"

def send_verification_email(to_email: str, token: str) -> bool:
    """
    Send account verification email using Resend
    Returns True on success, False on failure
    """
    if not resend_client.api_key:
        print("[email] RESEND_API_KEY is missing in environment variables")
        return False

    verify_link = _build_verify_link(token)
    html = f"""
    <div style="font-family:system-ui,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <h2>{UI_BRAND_NAME}</h2>
        <p>Hello,</p>
        <p>Thank you for signing up! Please verify your email address:</p>
        <p style="margin:30px 0;">
            <a href="{verify_link}" 
               style="background:#6ea8fe;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;display:inline-block;font-weight:600;">
                Verify My Email
            </a>
        </p>
        <p style="color:#666;font-size:14px;">
            Or copy and paste this link: {verify_link}<br>
            This link will expire in 3 days.
        </p>
        <p style="margin-top:30px;color:#888;font-size:13px;">
            If you didn't create an account, you can safely ignore this email.
        </p>
    </div>
    """

    try:
        response = resend_client.emails.send({
            "from": f"{UI_BRAND_NAME} <onboarding@resend.dev>",  # Change to your domain later
            "to": [to_email],
            "subject": f"Verify your {UI_BRAND_NAME} account",
            "html": html,
        })
        print(f"[verification] Email sent to {to_email} → Message ID: {response['id']}")
        return True
    except Exception as e:
        print(f"[verification] Failed to send email: {str(e)}")
        return False


def send_magic_login_email(to_email: str, token: str) -> bool:
    """
    Send passwordless magic login link using Resend
    Returns True on success, False on failure
    """
    if not resend_client.api_key:
        print("[magic] RESEND_API_KEY is missing")
        return False

    login_link = _build_magic_link(token)
    html = f"""
    <div style="font-family:system-ui,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <h2>{UI_BRAND_NAME} — Magic Login</h2>
        <p>Hello,</p>
        <p>Use this link to sign in instantly (no password needed):</p>
        <p style="margin:30px 0;">
            <a href="{login_link}" 
               style="background:#6ea8fe;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;display:inline-block;font-weight:600;">
                Sign In Now
            </a>
        </p>
        <p style="color:#666;font-size:14px;">
            Or copy and paste: {login_link}<br>
            This link expires in 15 minutes for your security.
        </p>
        <p style="margin-top:30px;color:#888;font-size:13px;">
            If you didn't request this, please ignore this email.
        </p>
    </div>
    """

    try:
        response = resend_client.emails.send({
            "from": f"{UI_BRAND_NAME} <onboarding@resend.dev>",
            "to": [to_email],
            "subject": f"Your {UI_BRAND_NAME} Magic Login Link",
            "html": html,
        })
        print(f"[magic] Login link sent to {to_email} → Message ID: {response['id']}")
        return True
    except Exception as e:
        print(f"[magic] Failed to send login link: {str(e)}")
        return False
