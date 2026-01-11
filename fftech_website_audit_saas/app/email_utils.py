import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

UI_BRAND_NAME = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")


def _build_verify_link(token: str) -> str:
    return f"{BASE_URL.rstrip('/')}/auth/verify?token={token}"


def send_verification_email(to_email: str, token: str) -> bool:
    """Send account verification email using SMTP settings.
    Returns True on success, False otherwise.
    """
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        print("[email] Missing SMTP env vars (SMTP_HOST/SMTP_USER/SMTP_PASSWORD).")
        return False

    verify_link = _build_verify_link(token)
    subject = f"{UI_BRAND_NAME} – Verify your account"
    html_body = f"""
    <h3>{UI_BRAND_NAME}</h3>
    <p>Thanks for signing up! Please verify your account.</p>
    <p><a href='{verify_link}' target='_blank' rel='noopener noreferrer'>{verify_link}</a></p>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"[email] SMTP send failed: {e}")
        return False
