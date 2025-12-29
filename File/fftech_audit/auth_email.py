
# fftech_audit/auth_email.py
import os, time, hmac, hashlib, base64, smtplib
from email.message import EmailMessage
from typing import Dict, Any

SECRET = os.getenv('SECRET_KEY', 'dev-secret-change-me')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')
FROM_EMAIL = os.getenv('FROM_EMAIL', 'no-reply@fftech.ai')
SMTP_HOST = os.getenv('SMTP_HOST')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASS = os.getenv('SMTP_PASS')

# --- Tiny token helper (HMAC-signed) ---
def _sign(data: bytes) -> str:
    sig = hmac.new(SECRET.encode('utf-8'), data, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode('utf-8')

def generate_token(payload: Dict[str, Any], ttl_seconds: int = 3600) -> str:
    payload = dict(payload)
    payload['exp'] = int(time.time()) + ttl_seconds
    raw = base64.urlsafe_b64encode(str(payload).encode('utf-8'))
    sig = _sign(raw)
    return raw.decode('utf-8') + '.' + sig


def _decode_token(token: str) -> Dict[str, Any]:
    if '.' not in token:
        raise ValueError('Invalid token format')
    raw_b64, sig = token.split('.', 1)
    raw = raw_b64.encode('utf-8')
    if _sign(raw) != sig:
        raise ValueError('Invalid signature')
    payload_str = base64.urlsafe_b64decode(raw).decode('utf-8')
    data = {}
    for part in payload_str.strip('{}').split(','):
        if ':' in part:
            k, v = part.split(':', 1)
            k = k.strip().strip("'"")
            v = v.strip().strip("'"")
            if k == 'exp':
                data[k] = int(v)
            else:
                data[k] = v
    return data


def verify_session_token(token: str) -> Dict[str, Any]:
    data = _decode_token(token)
    if data.get('exp', 0) < int(time.time()):
        raise ValueError('Token expired')
    return data


def verify_magic_or_verify_link(token: str) -> str:
    data = verify_session_token(token)
    email = data.get('email')
    if not email:
        raise ValueError('Email missing in token')
    return email


def send_verification_link(email: str):
    token = generate_token({'email': email, 'purpose': 'verify'}, ttl_seconds=3600)
    verify_url = f"{BASE_URL}/auth/verify-link?token={token}"
    subject = 'Your FF Tech AI secure login link'
    body = f"Click to complete registration: {verify_url}

This link expires in 60 minutes."
    _send_email(email, subject, body)


def send_email_with_pdf(to_email: str, subject: str, body: str, pdf_bytes: bytes):
    msg = EmailMessage()
    msg['From'] = FROM_EMAIL
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.set_content(body)
    msg.add_attachment(pdf_bytes, maintype='application', subtype='pdf', filename='FFTech_Audit.pdf')
    _deliver(msg)


def _send_email(to_email: str, subject: str, body: str):
    msg = EmailMessage()
    msg['From'] = FROM_EMAIL
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.set_content(body)
    _deliver(msg)


def _deliver(msg: EmailMessage):
    if not SMTP_HOST:
        print('[EMAIL] SMTP not configured; printing email instead:')
        print(msg)
        return
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        if SMTP_USER and SMTP_PASS:
            server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
        print('[EMAIL] Sent to', msg['To'])
