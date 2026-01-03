
import os, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST = os.getenv('SMTP_HOST')
SMTP_PORT = int(os.getenv('SMTP_PORT','587'))
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
BASE_URL = os.getenv('BASE_URL','http://localhost:8000')
UI_BRAND_NAME = os.getenv('UI_BRAND_NAME','FF Tech')

def send_verification_email(to_email: str, token: str):
    verify_url = f"{BASE_URL}/verify?token={token}"
    subject = f"{UI_BRAND_NAME} – Verify your email"
    html = f"""
    <p>Welcome to {UI_BRAND_NAME}!</p>
    <p>Please verify your email by clicking the link below:</p>
    <p><a href='{verify_url}'>Verify my email</a></p>
    <p>If you didn't sign up, you can ignore this email.</p>
    """
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = SMTP_USER
    msg['To'] = to_email
    msg.attach(MIMEText(html, 'html'))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, [to_email], msg.as_string())
