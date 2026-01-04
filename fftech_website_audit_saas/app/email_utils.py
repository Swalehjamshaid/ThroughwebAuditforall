
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST     = os.getenv('SMTP_HOST')
SMTP_PORT     = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER     = os.getenv('SMTP_USER')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
BASE_URL      = os.getenv('BASE_URL', 'http://localhost:8000')

def send_verification_email(to_email: str, token: str) -> bool:
    """
    Sends a simple verification email with a link to /verify?token=...
    Returns True on success, False otherwise.
    """
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        # No SMTP configured; skip without failing registration
        return False

    verify_link = f"{BASE_URL}/verify?token={token}"
    subject = "Verify your FF Tech account"
    html    = f"""
    <h3>Verify your account</h3>
    <p>Please click the link below to verify your email:</p>
    <p>{verify_link}{verify_link}</a></p>
    """

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = SMTP_USER
    msg['To']      = to_email
    msg.attach(MIMEText(html, 'html'))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [to_email], msg.as_string())
        return True
    except Exception:
        return False
