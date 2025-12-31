
import smtplib
from email.mime.text import MIMEText
from .settings import settings

def smtp_configured() -> bool:
    return all([settings.SMTP_HOST, settings.SMTP_PORT, settings.SMTP_USER, settings.SMTP_PASS, settings.EMAIL_FROM])

def send_email(to: str, subject: str, html_body: str) -> bool:
    if not smtp_configured():
        return False
    msg = MIMEText(html_body, 'html')
    msg['Subject'] = subject
    msg['From'] = settings.EMAIL_FROM
    msg['To'] = to
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASS)
            server.send_message(msg)
        return True
    except Exception:
        return False
