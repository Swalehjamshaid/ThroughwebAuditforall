
# fftech_audit/auth_email.py
import os, ssl, json, time, hmac, hashlib, base64, random, string, datetime
from typing import Dict, Any
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session
from passlib.hash import bcrypt

from .db import User, MagicLink, EmailCode

SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_SECRET_32+CHARS")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587")) if os.getenv("SMTP_PORT") else None
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@fftech.example")

def now_utc() -> datetime.datetime:
    return datetime.datetime.utcnow()

def base64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")

def base64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "==")

def generate_token(payload: Dict[str, Any], exp_minutes: int = 60*24*30) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = dict(payload)
    payload["exp"] = int(time.time()) + exp_minutes * 60
    h_b64 = base64url(json.dumps(header).encode())
    p_b64 = base64url(json.dumps(payload).encode())
    signing_input = f"{h_b64}.{p_b64}".encode()
    sig = hmac.new(SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()
    s_b64 = base64url(sig)
    return f"{h_b64}.{p_b64}.{s_b64}"

def verify_session_token(token: str) -> Dict[str, Any]:
    try:
        h_b64, p_b64, s_b64 = token.split(".")
        signing_input = f"{h_b64}.{p_b64}".encode()
        expected = hmac.new(SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()
        given = base64url_decode(s_b64)
        if not hmac.compare_digest(expected, given):
            raise ValueError("Bad signature")
        payload = json.loads(base64url_decode(p_b64))
        if int(time.time()) > payload.get("exp", 0):
            raise ValueError("Expired")
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

# ------------- Verification Link -------------
def send_verification_link(email: str, request: Request, db: Session):
    email = email.lower().strip()
    token = generate_token({"email": email, "purpose": "verify"}, exp_minutes=60*24)
    ml = MagicLink(email=email, token=token, purpose="verify",
                   expires_at=now_utc() + datetime.timedelta(days=1), used=False)
    db.add(ml); db.commit()
    verify_url = f"{str(request.base_url).rstrip('/')}/auth/verify-link?token={token}"
    print(f"[DEV] Verification link for {email}: {verify_url}")

    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASS and SMTP_FROM):
        return

    subject = "FF Tech • Verify your account"
    body = f"Hello,\n\nClick to verify your account:\n{verify_url}\n\nLink valid for 24 hours."
    message = f"From: {SMTP_FROM}\r\nTo: {email}\r\nSubject: {subject}\r\n\r\n{body}"

    import smtplib
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=context); server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_FROM, [email], message)

def verify_magic_or_verify_link(token: str, db: Session) -> str:
    """Accept both magic login and verify token; mark verified, issue session JWT."""
    try:
        h_b64, p_b64, s_b64 = token.split(".")
        signing_input = f"{h_b64}.{p_b64}".encode()
        expected = hmac.new(SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()
        given = base64url_decode(s_b64)
        if not hmac.compare_digest(expected, given):
            raise ValueError("Bad signature")
        payload = json.loads(base64url_decode(p_b64))
        if int(time.time()) > payload.get("exp", 0):
            raise ValueError("Expired")
        purpose = payload.get("purpose")
        email = payload.get("email")
        if purpose not in ("magic", "verify"):
            raise ValueError("Invalid purpose")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid link: {e}")

    ml = db.query(MagicLink).filter(MagicLink.token == token).first()
    if not ml or ml.used or ml.expires_at < now_utc():
        raise HTTPException(status_code=400, detail="Link invalid or expired")

    ml.used = True
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, verified=True, plan="free")  # may be created later in /auth/register
        db.add(user)
    else:
        user.verified = True
    db.commit()

    session_token = generate_token({"email": email, "purpose": "session"})
    return session_token

# ------------- Password Utilities -------------
def hash_password(plain: str) -> str:
    return bcrypt.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.verify(plain, hashed)
    except Exception:
        return False

# ------------- OTP (optional) -------------
def send_verification_code(email: str, request: Request, db: Session):
    code = "".join(random.choices("0123456789", k=6))
    rec = EmailCode(email=email.lower().strip(), code=code, expires_at=now_utc() + datetime.timedelta(minutes=30), used=False)
    db.add(rec); db.commit()
    print(f"[DEV] Verification code for {email}: {code}")

    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASS and SMTP_FROM):
        return

    subject = "Your FF Tech verification code"
    body = f"Your verification code is: {code}\n\nIt expires in 30 minutes."
    message = f"From: {SMTP_FROM}\r\nTo: {email}\r\nSubject: {subject}\r\n\r\n{body}"

    import smtplib
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=context); server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_FROM, [email], message)

def verify_email_code_and_issue_token(email: str, code: str, db: Session) -> str:
    rec = db.query(EmailCode).filter(EmailCode.email == email.lower().strip(), EmailCode.code == code).order_by(EmailCode.created_at.desc()).first()
    if not rec: raise HTTPException(status_code=400, detail="Invalid code")
    if rec.used: raise HTTPException(status_code=400, detail="Code already used")
    if rec.expires_at < now_utc(): raise HTTPException(status_code=400, detail="Code expired")

    rec.used = True
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user:
        user = User(email=email.lower().strip(), verified=True, plan="free")
        db.add(user)
    else:
        user.verified = True
    db.commit()

    return generate_token({"email": email.lower().strip(), "purpose": "session"})

# ------------- Email with PDF (for scheduler) -------------
def send_email_with_pdf(email: str, subject: str, body: str, pdf_bytes: bytes, filename: str = "FFTech_Audit.pdf"):
    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASS and SMTP_FROM):
        print("[DEV] SMTP not configured; skipping email send.")
        return
    boundary = "===============%s==" % ("".join(random.choices(string.ascii_letters+string.digits, k=24)))
    header = [
        f"From: {SMTP_FROM}",
        f"To: {email}",
        f"Subject: {subject}",
        "MIME-Version: 1.0",
        f"Content-Type: multipart/mixed; boundary=\"{boundary}\"",
        "",
        f"--{boundary}",
        "Content-Type: text/plain; charset=\"utf-8\"",
        "",
        body,
        f"--{boundary}",
        f"Content-Type: application/pdf; name=\"{filename}\"",
        "Content-Transfer-Encoding: base64",
        f"Content-Disposition: attachment; filename=\"{filename}\"",
        "",
        base64.b64encode(pdf_bytes).decode(),
        f"--{boundary}--",
        ""
    ]
    message = "\r\n".join(header)
    import smtplib
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=context); server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_FROM, [email], message)
