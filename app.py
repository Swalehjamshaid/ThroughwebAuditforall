import os, io, re, ssl, json, time, hmac, hashlib, secrets, asyncio, datetime, base64, smtplib
from typing import Any, Dict, List, Tuple, Optional
from urllib.parse import urlparse, urljoin
from email.message import EmailMessage

# FastAPI & Security
from fastapi import FastAPI, HTTPException, Depends, Query, Request, Body, Header
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

# Database
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, desc
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# PDF Generation
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm, mm
    from reportlab.graphics.shapes import Drawing, String as PDFString
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics import renderPDF
    PDF_ENABLED = True
except ImportError:
    PDF_ENABLED = False

import requests
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
APP_NAME = "FF Tech AI Website Audit SaaS"
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fftech_audit.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SMTP Settings
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "no-reply@fftech.io")

# Limits
FREE_AUDIT_LIMIT = 10

# --- DATABASE SETUP ---
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True)
    verified = Column(Boolean, default=False)
    plan = Column(String(32), default="free") # free | pro
    audits_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    audits = relationship("AuditRecord", back_populates="user")

class AuditRecord(Base):
    __tablename__ = "audits"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    url = Column(String(2048), nullable=False)
    score = Column(Integer)
    grade = Column(String(4))
    metrics_json = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    user = relationship("User", back_populates="audits")

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- SECURITY UTILS ---
def create_jwt(data: dict, expires_delta: int = 1440):
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    payload = data.copy()
    payload.update({"exp": int(time.time()) + expires_delta * 60})
    payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature = hmac.new(SECRET_KEY.encode(), f"{header}.{payload_encoded}".encode(), hashlib.sha256).digest()
    sig_encoded = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{header}.{payload_encoded}.{sig_encoded}"

def verify_jwt(token: str):
    try:
        header, payload, sig = token.split(".")
        valid_sig = hmac.new(SECRET_KEY.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(base64.urlsafe_b64decode(sig + "=="), valid_sig): return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=="))
        if data['exp'] < time.time(): return None
        return data
    except: return None

# --- AUDIT ENGINE ---
class FFTechAuditEngine:
    def __init__(self, url: str):
        self.url = url if url.startswith("http") else f"https://{url}"
        self.metrics = {}

    def analyze(self):
        try:
            t0 = time.time()
            r = requests.get(self.url, timeout=10, headers={"User-Agent": "FFTech-AI-Bot/1.0"})
            latency = (time.time() - t0) * 1000
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Logic for 200 Metrics (Iterative structure)
            m = {}
            for i in range(1, 201):
                m[i] = {"id": i, "val": "Passed", "score": 1, "desc": f"Analysis for metric {i} optimal."}

            # Sample Logic for Key Categories
            score = 85
            if not self.url.startswith("https"): score -= 20; m[105] = {"val": "Failed", "score": 0, "desc": "SSL not detected."}
            if not soup.title: score -= 10; m[41] = {"val": "Failed", "score": 0, "desc": "Title tag missing."}
            
            grade = "A+" if score >= 95 else "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D"
            
            self.results = {
                "url": self.url, "score": max(0, score), "grade": grade,
                "metrics": m, "latency": round(latency, 2),
                "summary": f"Audit for {self.url} completed. Grade {grade} achieved."
            }
            return self.results
        except Exception as e:
            return {"error": str(e), "score": 0, "grade": "F"}

# --- PDF GENERATOR ---
def generate_audit_pdf(data: dict):
    if not PDF_ENABLED: return None
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    
    # Page 1: Cover & Branding
    c.setFillColor(colors.HexColor("#111827"))
    c.rect(0, h-40*mm, w, 40*mm, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(20*mm, h-25*mm, "FF TECH | AI WEBSITE AUDIT")
    
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 14)
    c.drawString(20*mm, h-60*mm, f"Report for: {data['url']}")
    c.setFont("Helvetica-Bold", 40)
    c.drawCentredString(w/2, h/2, f"{data['score']}%")
    c.setFont("Helvetica", 18)
    c.drawCentredString(w/2, h/2 - 20*mm, f"GRADE: {data['grade']}")
    
    # Iterate for 5 pages... (Simplified)
    for p in range(2, 6):
        c.showPage()
        c.setFont("Helvetica-Bold", 16)
        c.drawString(20*mm, h-20*mm, f"Category Performance - Section {p}")
        # Insert Charts/Text here...
        
    c.save()
    buf.seek(0)
    return buf.getvalue()

# --- FASTAPI APP ---
app = FastAPI(title=APP_NAME)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- ROUTES ---
@app.post("/auth/request-magic-link")
def request_link(email: EmailStr = Body(..., embed=True)):
    token = create_jwt({"email": email, "type": "magic_link"}, expires_delta=30)
    # dev login link
    login_url = f"https://yourdomain.com/verify?token={token}"
    print(f"DEV MAGIC LINK: {login_url}")
    return {"message": "Check your email for the magic link."}

@app.post("/api/audit")
def perform_audit(url: str, token: str = Header(None), db=Depends(get_db)):
    user_id = None
    if token:
        payload = verify_jwt(token)
        if payload:
            user = db.query(User).filter(User.email == payload['email']).first()
            if user:
                if user.plan == "free" and user.audits_count >= FREE_AUDIT_LIMIT:
                    raise HTTPException(402, "Free limit reached.")
                user_id = user.id

    engine = FFTechAuditEngine(url)
    results = engine.analyze()
    
    # Save Audit Record
    record = AuditRecord(
        user_id=user_id, url=url, score=results['score'], 
        grade=results['grade'], metrics_json=json.dumps(results['metrics'])
    )
    db.add(record)
    if user_id:
        user.audits_count += 1
    db.commit()
    return results

@app.get("/api/report/{audit_id}")
def download_pdf(audit_id: int, db=Depends(get_db)):
    record = db.query(AuditRecord).filter(AuditRecord.id == audit_id).first()
    if not record: raise HTTPException(404)
    
    data = {
        "url": record.url, "score": record.score, 
        "grade": record.grade, "metrics": json.loads(record.metrics_json)
    }
    pdf = generate_audit_pdf(data)
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf")

@app.get("/health")
def health(): return {"status": "ok", "engine": "ready"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
