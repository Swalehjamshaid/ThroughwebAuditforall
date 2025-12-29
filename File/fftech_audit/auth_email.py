
import os, hmac, hashlib, base64
from datetime import datetime, timedelta
from .db import MagicLink, SessionLocal
import smtplib
from email.mime.text import MIMEText

SECRET = os.getenv('EMAIL_TOKEN_SECRET', 'change-me')
BASE_URL = os.getenv('BASE_URL', 'https://your-service.example')
SENDER = os.getenv('EMAIL_SENDER', 'no-reply@example.com')

def generate_token(data: dict) -> str:
    payload = base64.urlsafe_b64encode(str(data).encode()).decode()
    sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{base64.urlsafe_b64encode(sig).decode()}"

def send_email(to, subject, body):
    msg = MIMEText(body, 'html')
    msg['Subject'] = subject
    msg['From'] = SENDER
    msg['To'] = to
    print(f"[EMAIL] {to}: {subject}\n{body}")  # Replace with SMTP for production

def send_verification_link(email):
    token = generate_token({'email': email, 'purpose': 'verify'})
    link = f"{BASE_URL}/auth/verify-link?token={token}"
    send_email(email, 'Verify your email', f"{link}Click to verify</a>")
    db = SessionLocal()
    ml = MagicLink(email=email, token=token, purpose='verify',
                   created_at=datetime.utcnow(),
                   expires_at=datetime.utcnow() + timedelta(hours=24),
                   consumed=False)
    db.add(ml); db.commit(); db.close()
