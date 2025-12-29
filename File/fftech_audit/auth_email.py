
# fftech_audit/auth_email.py
import os, hmac, hashlib, base64
from datetime import datetime, timedelta
from .db import MagicLink, SessionLocal
import smtplib
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart

SECRET   = os.getenv('EMAIL_TOKEN_SECRET', 'change-me')
BASE_URL = os.getenv('BASE_URL', 'https://your-service.example')
SENDER   = os.getenv('EMAIL_SENDER', 'no-reply@example.com')
SMTP_HOST= os.getenv('SMTP_HOST', '')
SMTP_PORT= int(os.getenv('SMTP_PORT', '587'))
SMTP_USER= os.getenv('SMTP_USER', '')
SMTP_PASS= os.getenv('SMTP_PASS', '')

def _sign(payload: str) -> str:
    sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode()

def generate_token(data: dict) -> str:
    payload = base64.urlsafe_b64encode(str(data).encode()).decode()
    return f"{payload}.{_sign(payload)}"

def verify_token(token: str) -> dict:
    payload, sig = token.split('.')
    if _sign(payload) != sig: raise ValueError('bad signature')
    raw = base64.urlsafe_b64decode(payload.encode()).decode()
    return eval(raw)  # for trusted environment; prefer json in production

def send_email(to: str, subject: str, html_body: str):
    if not SMTP_HOST:
        print(f"[EMAIL] {to} :: {subject}\n{html_body}")
        return
    msg = MIMEText(html_body, 'html')
    msg['Subject'] = subject; msg['From'] = SENDER; msg['To'] = to
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        if SMTP_USER: server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

def send_email_with_pdf(to: str, subject: str, html_body: str, pdf_bytes: bytes, filename: str="FFTech_Audit.pdf"):
    if not SMTP_HOST:
        print(f"[EMAIL+PDF] {to} :: {subject} :: bytes={len(pdf_bytes)}")
        return
    msg = MIMEMultipart()
    msg['Subject']=subject; msg['From']=SENDER; msg['To']=to
    msg.attach(MIMEText(html_body, 'html'))
    part = MIMEApplication(pdf_bytes, _subtype='pdf')
    part.add_header('Content-Disposition', 'attachment', filename=filename)
    msg.attach(part)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        if SMTP_USER: server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

def send_verification_link(email: str):
    token = generate_token({'email': email, 'purpose': 'verify', 'ts': datetime.utcnow().isoformat()})
    link  = f"{BASE_URL}/auth/verify-link?token={token}"
    send_email(email, 'Verify your email', f"<p>Click to verify your email:</p><p>{link}{link}</a></p>")
    db = SessionLocal()
    ml = MagicLink(email=email, token=token, purpose='verify',
                   created_at=datetime.utcnow(),
                   expires_at=datetime.utcnow() + timedelta(hours=24),
                   consumed=False)
    db.add(ml); db.commit(); db.close()

def verify_magic_or_verify_link(token: str) -> str:
    data = verify_token(token); email = data.get('email')
    db = SessionLocal()
    try:
        ml = db.query(MagicLink).filter(MagicLink.token == token, MagicLink.consumed == False).first()
        if not ml: raise ValueError('link not found')
        if ml.expires_at < datetime.utcnow(): raise ValueError('link expired')
        ml.consumed = True; db.commit()
    finally:
        db.close()
    return email

def verify_session_token(token: str) -> dict: return verify_token(token)
def hash_password(pw: str) -> str: return hashlib.sha256(pw.encode()).hexdigest()
def verify_password(pw: str, hashed: str) -> bool: return hashlib.sha256(pw.encode()).hexdigest() == hashed
