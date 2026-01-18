
import smtplib
from email.mime.text import MIMEText
from .config import settings

def send_email(to_email: str, subject: str, html_body: str):
    if not (settings.SMTP_HOST and settings.SMTP_FROM and settings.SMTP_USER and settings.SMTP_PASS):
        print("[WARN] SMTP not configured. Email not sent. Link below for dev:")
        print(html_body)
        return
    msg = MIMEText(html_body, 'html')
    msg['Subject'] = subject
    msg['From'] = settings.SMTP_FROM
    msg['To'] = to_email
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as s:
        s.starttls()
        s.login(settings.SMTP_USER, settings.SMTP_PASS)
        s.sendmail(settings.SMTP_FROM, [to_email], msg.as_string())
