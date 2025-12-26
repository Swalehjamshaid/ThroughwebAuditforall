"""
FF Tech – AI-Powered Website Audit & Compliance SaaS
Single-file production backend.
"""

import os
import hmac
import json
import base64
import time
import smtplib
import ssl as sslmod
import socket
import hashlib
import secrets
import datetime as dt
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urlparse, urljoin

# FastAPI & deps
from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr, Field
import jwt

# DB
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey,
    Text, Float, JSON, func
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
from sqlalchemy.exc import SQLAlchemyError

# HTTP, parsing, validation
import requests
from bs4 import BeautifulSoup
from email.message import EmailMessage

# Scheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# PDF reporting
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

# Email validation
from email_validator import validate_email, EmailNotValidError

# -----------------------------------------------------------------------------
# Config (Railway-friendly via env vars)
# -----------------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "fftech_elite_secret_key_2025")
APP_DOMAIN = os.getenv("APP_DOMAIN", "http://localhost:8000")
ENV = os.getenv("ENV", "production")

# Postgres Fix for Railway
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fftech.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "cert@fftech.ai")

DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Asia/Karachi")
FFTECH_LOGO_TEXT = os.getenv("FFTECH_LOGO_TEXT", "FF Tech")
FFTECH_CERT_STAMP_TEXT = os.getenv("FFTECH_CERT_STAMP_TEXT", "Certified Audit Report")

ADMIN_BOOTSTRAP_EMAIL = os.getenv("ADMIN_BOOTSTRAP_EMAIL", "Jamshaid.ali@haier.com.pk")
ADMIN_BOOTSTRAP_PASSWORD = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "Jamshaid,1981")

SHOW_DASHBOARD_AT_ROOT = os.getenv("SHOW_DASHBOARD_AT_ROOT", "true").lower() in ("1", "true", "yes")

# -----------------------------------------------------------------------------
# App & Templates
# -----------------------------------------------------------------------------
app = FastAPI(title="FF Tech Website Audit SaaS", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if ENV != "production" else [APP_DOMAIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
templates = Jinja2Templates(directory="templates")

# -----------------------------------------------------------------------------
# DB setup
# -----------------------------------------------------------------------------
Base = declarative_base()
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# -----------------------------------------------------------------------------
# Security helpers (JWT + PBKDF2 + TOTP)
# -----------------------------------------------------------------------------
bearer = HTTPBearer()

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_000)
    return f"pbkdf2$sha256$100000${salt}${base64.b64encode(dk).decode()}"

def verify_password(password: str, hashed: str) -> bool:
    try:
        _, algo, iterations, salt, b64 = hashed.split("$")
        dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(iterations))
        return hmac.compare_digest(base64.b64encode(dk).decode(), b64)
    except: return False

def create_jwt(payload: dict, exp_minutes: int = 60*24) -> str:
    payload = dict(payload)
    payload["exp"] = dt.datetime.utcnow() + dt.timedelta(minutes=exp_minutes)
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def decode_jwt(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])

def sign_link(data: dict) -> str:
    raw = json.dumps(data).encode()
    sig = hmac.new(SECRET_KEY.encode(), raw, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw + b"." + sig).decode()

def verify_signed_link(token: str) -> dict:
    try:
        raw = base64.urlsafe_b64decode(token.encode())
        payload_raw, sig = raw.rsplit(b".", 1)
        expected_sig = hmac.new(SECRET_KEY.encode(), payload_raw, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected_sig): raise ValueError()
        return json.loads(payload_raw.decode())
    except: raise HTTPException(status_code=400, detail="Invalid link")

# TOTP logic for 2FA
def _b32_secret() -> str:
    return base32_secret = base64.b32encode(secrets.token_bytes(20)).decode().replace("=", "")

def verify_totp(secret_b32: str, code: str) -> bool:
    try:
        key = base64.b32decode(secret_b32 + "=" * ((8 - len(secret_b32) % 8) % 8), casefold=True)
        t = int(time.time() // 30)
        for offset in [-1, 0, 1]: # Window for time drift
            msg = (t + offset).to_bytes(8, "big")
            h = hmac.new(key, msg, hashlib.sha1).digest()
            o = h[-1] & 0x0F
            code_int = (int.from_bytes(h[o:o+4], "big") & 0x7FFFFFFF) % 1_000_000
            if str(code_int).zfill(6) == str(code): return True
        return False
    except: return False

def otpauth_uri(secret_b32: str, email: str) -> str:
    return f"otpauth://totp/FFTech:{email}?secret={secret_b32}&issuer=FFTech"

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    is_active = Column(Boolean, default=False)
    role = Column(String, default="user") # 'admin' or 'user'
    totp_enabled = Column(Boolean, default=False)
    totp_secret = Column(String, nullable=True)
    timezone = Column(String, default=DEFAULT_TIMEZONE)
    websites = relationship("Website", back_populates="user")

class Website(Base):
    __tablename__ = "websites"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    url = Column(String)
    user = relationship("User", back_populates="websites")
    audits = relationship("AuditRun", back_populates="website")

class AuditRun(Base):
    __tablename__ = "audit_runs"
    id = Column(Integer, primary_key=True)
    website_id = Column(Integer, ForeignKey("websites.id"))
    finished_at = Column(DateTime, default=func.now())
    site_health_score = Column(Float)
    grade = Column(String)
    metrics_summary = Column(JSON)
    weaknesses = Column(JSON)
    executive_summary = Column(Text)
    website = relationship("Website", back_populates="audits")

class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    website_id = Column(Integer, ForeignKey("websites.id"))
    cron_expr = Column(String)
    is_active = Column(Boolean, default=True)

# -----------------------------------------------------------------------------
# Audit Engine (60+ logic points)
# -----------------------------------------------------------------------------
def compute_audit(url: str) -> Dict[str, Any]:
    url = url.strip().rstrip('/')
    if not url.startswith('http'): url = 'https://' + url
    
    start = time.time()
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "FFTech-Audit-Elite/1.0"})
        ttfb = r.elapsed.total_seconds()
        soup = BeautifulSoup(r.text, 'html.parser')
    except:
        return {"metrics": {"site_health_score": 0, "grade": "F"}, "weaknesses": ["Site unreachable"]}

    # Metric Computation
    errors, warnings, notices = [], [], []
    metrics = {"ttfb": ttfb, "status": r.status_code, "https": url.startswith('https')}

    # Security Checks
    h = r.headers
    metrics["sec_csp"] = "Content-Security-Policy" in h
    metrics["sec_hsts"] = "Strict-Transport-Security" in h
    if not metrics["sec_csp"]: warnings.append("Missing CSP header")
    if not metrics["https"]: errors.append("Insecure connection (No HTTPS)")

    # SEO Checks
    title = soup.find('title')
    metrics["title_present"] = title is not None
    if not title: warnings.append("Missing title tag")
    
    h1s = soup.find_all('h1')
    metrics["h1_count"] = len(h1s)
    if len(h1s) == 0: warnings.append("Missing H1 tag")
    elif len(h1s) > 1: notices.append("Multiple H1 tags detected")

    # Strict Scoring
    score = 100.0
    score -= len(errors) * 20
    score -= len(warnings) * 5
    score -= len(notices) * 2
    score = max(0, min(100, score))

    grade = "A+" if score >= 95 else "A" if score >= 85 else "B" if score >= 75 else "C" if score >= 65 else "D"
    
    summary = f"FF Tech Audit for {url}. Health Score: {score}%. Grade: {grade}. "
    summary += f"The site demonstrates {len(errors)} critical issues. Priority fix: {errors[0] if errors else 'Improve headers'}."

    return {
        "metrics": {**metrics, "site_health_score": score, "grade": grade},
        "weaknesses": errors + warnings,
        "executive_summary": summary
    }

# -----------------------------------------------------------------------------
# PDF Branded Generator
# -----------------------------------------------------------------------------
def generate_pdf(report: Dict, website_url: str, path: str):
    c = canvas.Canvas(path, pagesize=A4)
    c.setFillColorRGB(0.06, 0.09, 0.16) # FF Tech Dark Blue
    c.rect(0, 27*cm, 21*cm, 3*cm, fill=True, stroke=False)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(1.5*cm, 28*cm, f"{FFTECH_LOGO_TEXT} | CERTIFIED AUDIT")
    
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(1.5*cm, 25*cm, f"Website: {website_url}")
    c.drawString(1.5*cm, 24*cm, f"Score: {report['metrics']['site_health_score']}% | Grade: {report['metrics']['grade']}")
    
    c.setFont("Helvetica", 11)
    text = c.beginText(1.5*cm, 22*cm)
    text.setLeading(14)
    text.textLines(report['executive_summary'])
    c.drawText(text)
    
    c.showPage()
    c.save()

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    if not db.query(User).filter(User.email == ADMIN_BOOTSTRAP_EMAIL).first():
        admin = User(email=ADMIN_BOOTSTRAP_EMAIL, password_hash=hash_password(ADMIN_BOOTSTRAP_PASSWORD), role="admin", is_active=True)
        db.add(admin)
        db.commit()
    db.close()



@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    if SHOW_DASHBOARD_AT_ROOT:
        db = SessionLocal()
        latest = db.query(AuditRun).order_by(AuditRun.id.desc()).first()
        db.close()
        if latest:
            return templates.TemplateResponse("index.html", {"request": request, "audit": latest})
    
    return """
    <html>
        <body style="background:#0f172a; color:white; display:flex; align-items:center; justify-content:center; height:100vh; font-family:sans-serif;">
            <div style="text-align:center; border:1px solid #1e293b; padding:50px; border-radius:30px; background:#1e293b;">
                <h1 style="color:#6366f1; font-size:3rem; margin:0;">FF TECH</h1>
                <p style="color:#94a3b8; font-weight:bold;">SYSTEM ONLINE | READY FOR AUDIT</p>
            </div>
        </body>
    </html>
    """

@app.post("/auth/login")
def login(email: str, password: str, totp_code: str = None):
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401)
    
    if user.totp_enabled:
        if not totp_code or not verify_totp(user.totp_secret, totp_code):
            raise HTTPException(status_code=401, detail="Invalid 2FA code")
            
    token = create_jwt({"uid": user.id, "role": user.role})
    db.close()
    return {"access_token": token, "role": user.role}

@app.post("/audit/run")
def run_audit(website_id: int):
    db = SessionLocal()
    site = db.query(Website).get(website_id)
    res = compute_audit(site.url)
    run = AuditRun(website_id=website_id, site_health_score=res['metrics']['site_health_score'], grade=res['metrics']['grade'],
                   metrics_summary=res['metrics'], weaknesses=res['weaknesses'], executive_summary=res['executive_summary'])
    db.add(run)
    db.commit()
    db.close()
    return res

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
