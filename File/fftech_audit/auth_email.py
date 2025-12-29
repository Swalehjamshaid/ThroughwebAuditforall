
import os, smtplib
from email.mime.text import MIMEText
from itsdangerous import URLSafeSerializer

SECRET_KEY = os.getenv('SECRET_KEY', 'super-secret-key-change-me')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')
SENDER = os.getenv('FROM_EMAIL', 'no-reply@fftech.ai')
SMTP_HOST = os.getenv('SMTP_HOST')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASS = os.getenv('SMTP_PASS')

ser = URLSafeSerializer(SECRET_KEY, salt='fftech-email')

def generate_token(payload: dict) -> str:
    return ser.dumps(payload)

def verify_magic_or_verify_link(token: str) -> str:
    data = ser.loads(token)
    return data.get('email')

def verify_session_token(token: str) -> dict:
    return ser.loads(token)

def send_verification_link(email: str):
    token = generate_token({'email': email, 'purpose': 'verify'})
    link = f"{BASE_URL}/auth/verify-link?token={token}"
    body = f"""
    <h3>FF Tech AI • Website Audit</h3>
    <p>Click to verify and sign in:</p>
    <p><a href='{link}'>Verify & Sign In</a></p>
    """
    msg = MIMEText(body, 'html')
    msg['Subject'] = 'Verify your email • FF Tech AI'
    msg['From'] = SENDER
    msg['To'] = email
    if SMTP_HOST and SMTP_USER and SMTP_PASS:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
    else:
        print('[EMAIL] Would send to', email, 'link:', link)

def send_email_with_pdf(to_email: str, subject: str, text: str, pdf_bytes: bytes):
    # Minimal: log-only when SMTP not configured
    print(f"[EMAIL] PDF to {to_email} — bytes: {len(pdf_bytes)}")
