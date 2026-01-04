
# fftech_website_audit_saas/app/email_utils.py
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST     = os.getenv('SMTP_HOST')
SMTP_PORT     = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER     = os.getenv('SMTP_USER')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
BASE_URL      = os.getenv('BASE_URL', 'http://localhost:8000')  # <-- set to your Railway domain

def send_verification_email(to_email: str, token: str) -> bool:
    """
    Sends a simple verification email with a link to /verify?token=...
    Returns True on success, False otherwise.
    """
    # If SMTP is not configured, fail silently (registration shouldn't break)
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        return False

    # Build a proper clickable link
    verify_link = f"{BASE_URL}/verify?token={token}"

    subject = "Verify your FF Tech account"
    html    = f"""
    <h3>Verify your account</h3>
    <p>Please click the link below to verify your email:</p>
    <p>{verify_link}{verify_link}</a></p>
    <p
