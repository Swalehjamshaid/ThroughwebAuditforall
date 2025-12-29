# fftech_audit/auth_email.py
import os, ssl, json, time, hmac, hashlib, base64, random, string, datetime
from typing import Dict, Any
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session
from passlib.hash import bcrypt
from .db import User, MagicLink, EmailCode
from .audit_engine import now_utc

SECRET_KEY   = os.getenv("SECRET_KEY", "CHANGE_ME_32CHARS")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8080")
EMAIL_VERIFICATION_MODE = os.getenv("EMAIL_VERIFICATION_MODE", "link")  # "link" | "code"
ALLOW_DEV_VERIFY = os.getenv("ALLOW_DEV_VERIFY", "true").lower() == "true"

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@example.com")

# Token helpers

def base64url(b: bytes) -> str: return base64.urlsafe_b64encode(b).decode().rstrip("=")

def base64url_decode(s: str) -> bytes: return base64.urlsafe_b64decode(s + "==")

def generate_token(payload: Dict[str, Any], exp_minutes: int = 60*24) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = dict(payload); payload["exp"] = int(time.time()) + exp_minutes*60
    h_b64 = base64url(json.dumps(header).encode()); p_b64 = base64url(json.dumps(payload).encode())
    sig = hmac.new(SECRET_KEY.encode(), f"{h_b64}.{p_b64}".encode(), hashlib.sha256).digest()
    return f"{h_b64}.{p_b64}.{base64url(sig)}"


def verify_session_token(token: str) -> Dict[str, Any]:
    try:
        h_b64, p_b64, s_b64 = token.split(".")
        expected = hmac.new(SECRET_KEY.encode(), f"{h_b64}.{p_b64}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, base64url_decode(s_b64)): raise ValueError("Bad signature")
        payload = json.loads(base64url_decode(p_b64))
        if int(time.time()) > payload.get("exp", 0): raise ValueError("Expired")
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

# Password helpers

def hash_password(plain: str) -> str: return bcrypt.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    try: return bcrypt.verify(plain, hashed)
    except Exception: return False

# Email send

def _send_email(to_email: str, subject: str, body: str):
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS and SMTP_FROM):
        if ALLOW_DEV_VERIFY:
            print(f"[DEV EMAIL] To: {to_email}\nSubject: {subject}\n\n{body}")
            return
        else:
            raise RuntimeError("SMTP not configured and ALLOW_DEV_VERIFY=false")
    import smtplib
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=context)
        server.login(SMTP_USER, SMTP_PASS)
        message = f"From: {SMTP_FROM}\r\nTo: {to_email}\r\nSubject: {subject}\r\n\r\n{body}"
        server.sendmail(SMTP_FROM, [to_email], message)

# Verification flows

def send_verification_link(email: str, request: Request, db: Session):
    email = email.lower().strip()
    token = generate_token({"email": email, "purpose": "verify"}, exp_minutes=60*24)
    ml = MagicLink(email=email, token=token, purpose="verify",
                   expires_at=now_utc() + datetime.timedelta(days=1), used=False)
    db.add(ml); db.commit()
    verify_url = f"{APP_BASE_URL}/auth/verify-link?token={token}"

    if EMAIL_VERIFICATION_MODE == "code":
        code = "".join(random.choice(string.digits) for _ in range(6))
        rec = EmailCode(email=email, code=code, purpose="verify",
                        expires_at=now_utc() + datetime.timedelta(hours=2), used=False)
        db.add(rec); db.commit()
        body = f"Your verification code is: {code}\n\nOr click the link:\n{verify_url}\n\nExpires in 2 hours."
        _send_email(email, "FF Tech • Verify your account (code + link)", body)
    else:
        body = f"Click to verify your account:\n{verify_url}\n\nLink valid for 24 hours."
        _send_email(email, "FF Tech • Verify your account", body)

    print(f"[DEV] Verification link for {email}: {verify_url}")


def verify_magic_or_verify_link(token: str, db: Session) -> str:
    try:
        h_b64, p_b64, s_b64 = token.split(".")
        expected = hmac.new(SECRET_KEY.encode(), f"{h_b64}.{p_b64}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, base64url_decode(s_b64)): raise ValueError("Bad signature")
        payload = json.loads(base64url_decode(p_b64))
        if int(time.time()) > payload.get("exp", 0): raise ValueError("Expired")
        if payload.get("purpose") not in ("magic", "verify"): raise ValueError("Invalid purpose")
        email = payload.get("email")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid link: {e}")

    ml = db.query(MagicLink).filter(MagicLink.token == token).first()
    if not ml or ml.used or ml.expires_at < now_utc():
        raise HTTPException(status_code=400, detail="Link invalid or expired")

    ml.used = True
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, verified=True, plan="free")
        db.add(user)
    else:
        user.verified = True
    db.commit()

    return generate_token({"email": email, "purpose": "session"})

# Send email with PDF attachment (used by scheduler)

def send_email_with_pdf(to_email: str, subject: str, body_text: str, pdf_bytes: bytes, filename: str = "FFTech_Audit.pdf"):
    boundary = "BOUNDARY123"
    import base64 as b64
    message = (f"From: {SMTP_FROM}\r\nTo: {to_email}\r\nSubject: {subject}\r\nMIME-Version: 1.0\r\n" +
               f"Content-Type: multipart/mixed; boundary=\"{boundary}\"\r\n\r\n")
    message += f"--{boundary}\r\nContent-Type: text/plain\r\n\r\n{body_text}\r\n"
    message += (f"--{boundary}\r\nContent-Type: application/pdf; name=\"{filename}\"\r\n" +
                "Content-Transfer-Encoding: base64\r\n" +
                f"Content-Disposition: attachment; filename=\"{filename}\"\r\n\r\n")
    message += f"{b64.b64encode(pdf_bytes).decode()}\r\n--{boundary}--\r\n"

    if not (SMTP_HOST and SMTP_USER and SMTP_PASS and SMTP_FROM):
        if ALLOW_DEV_VERIFY:
            print(f"[DEV EMAIL] To: {to_email}\nSubject: {subject}\nAttachment: {filename} ({len(pdf_bytes)} bytes)")
            return
        else:
            raise RuntimeError("SMTP not configured and ALLOW_DEV_VERIFY=false")

    import smtplib
    ctx = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=ctx)
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_FROM, [to_email], message)
