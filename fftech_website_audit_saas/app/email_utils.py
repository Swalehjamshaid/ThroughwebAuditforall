import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST = os.getenv('SMTP_HOST')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')
VERIFICATION_PATH = os.getenv('VERIFICATION_PATH', '/auth/verify')


def send_verification_email(to_email: str, token: str) -> bool:
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        return False

    verify_link = f"{BASE_URL.rstrip('/')}{VERIFICATION_PATH}?token={token}"

    text_body = f"""Verify your account

Please open the following link to verify your email:
{verify_link}

If you didn't request this, you can ignore this message.
"""

    html_body = f"""<h4>Verify your account</h4>
<p>Please click the link below to verify your email:</p>
<p><a href="{verify_link}" target="_blank" rel="noopener noreferrer">{verify_link}</a></p>
<p>If you didn't request this, you can ignore this message.</p>
"""

    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Verify your FF Tech account'
    msg['From'] = SMTP_USER
    msg['To'] = to_email
    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, [to_email], msg.as_string())
        return True
    except Exception:
        return False
