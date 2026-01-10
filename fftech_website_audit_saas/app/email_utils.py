
from __future__ import annotations
import smtplib
from email.mime.text import MIMEText
from .services.config import SMTP_SERVER, SMTP_USER, SMTP_PASSWORD


def send_magic_link(email: str, link: str, logger) -> bool:
    if not SMTP_SERVER or not SMTP_USER or not SMTP_PASSWORD:
        logger.info('SMTP not configured; printing link to logs instead. %s -> %s', email, link)
        return True
    try:
        msg = MIMEText(f"Click to sign in: {link}")
        msg['Subject'] = 'FF Tech Audit Login Link'
        msg['From'] = SMTP_USER
        msg['To'] = email
        with smtplib.SMTP(SMTP_SERVER) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASSWORD)
            s.sendmail(SMTP_USER, [email], msg.as_string())
        return True
    except Exception as e:
        logger.error('Failed to send email: %s', e, exc_info=True)
        return False

