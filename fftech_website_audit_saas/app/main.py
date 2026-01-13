from __future__ import annotations

import os
import json
import asyncio
import logging
import smtplib
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, Generator, Iterable, Optional, Tuple
from urllib.parse import urlparse

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import FastAPI, Request, Form, Depends, Response, BackgroundTasks
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import Base, engine, SessionLocal
from .models import User, Website, Audit, Subscription
from .auth import hash_password, verify_password, create_token, decode_token
from .email_utils import send_verification_email
from .audit.engine import run_basic_checks
from .audit.grader import compute_overall, grade_from_score, summarize_200_words
from .audit.report import render_pdf

# ------------------------------------------------------------------------------
# 1. Configuration & Expanded Metrics (Preserved Attributes)
# ------------------------------------------------------------------------------
METRIC_LABELS: Dict[str, str] = {
    "status_code": "HTTP Status", "has_https": "SSL/TLS", "content_length": "Page Size",
    "hsts": "HSTS Header", "xfo": "X-Frame-Options", "csp": "Content-Security-Policy",
    "title": "Meta Title", "h1_count": "H1 Tags", "image_count": "Total Images",
    "viewport_present": "Mobile Responsive", "error": "Fetch Status"
}

def _env(*keys: str) -> Optional[str]:
    for k in keys:
        v = os.getenv(k)
        if v and v.strip(): return v.strip()
    return None

UI_BRAND_NAME: str = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")
SMTP_HOST: Optional[str] = _env("SMTP_HOST", "MAIL_HOST")
SMTP_PORT: int = int(_env("SMTP_PORT", "MAIL_PORT") or "587")
SMTP_USER: Optional[str] = _env("SMTP_USER", "EMAIL_USER")
SMTP_PASSWORD: Optional[str] = _env("SMTP_PASSWORD", "SMTP_PASS")
MAGIC_EMAIL_ENABLED: bool = os.getenv("MAGIC_EMAIL_ENABLED", "true").lower() == "true"
ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "roy.jamshaid@gmail.com")

# ------------------------------------------------------------------------------
# 2. FastAPI & Startup Patches
# ------------------------------------------------------------------------------
app = FastAPI(title=f"{UI_BRAND_NAME} — Website Audit SaaS")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

def inject_globals(request: Request):
    return {"datetime": datetime, "UI_BRAND_NAME": UI_BRAND_NAME, "year": datetime.utcnow().year}
templates.context_processors.append(inject_globals)

Base.metadata.create_all(bind=engine)
@app.on_event("startup")
async def startup_patches():
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS daily_time VARCHAR(8) DEFAULT '09:00';"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT FALSE;"))
            conn.execute(text("UPDATE users SET verified = True, is_admin = True WHERE email = :email"), {"email": ADMIN_EMAIL})
            conn.commit()
    except Exception as e: logging.warning(f"Startup error: {e}")

# ------------------------------------------------------------------------------
# 3. Helpers & Real Audit Logic (Fixed Undefined Metrics Error)
# ------------------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

async def get_current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("session_token")
    if not token: return None
    try:
        data = decode_token(token)
        return db.query(User).filter(User.id == data.get("uid")).first()
    except: return None

def _present_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in (metrics or {}).items():
        label = METRIC_LABELS.get(k, k.replace("_", " ").title())
        out[label] = "Pass ✅" if v is True else ("Fail ❌" if v is False else v)
    return out

def _perform_real_audit(url: str) -> Tuple[str, Dict[str, Any]]:
    u = url.strip()
    if not urlparse(u).scheme: u = "https://" + u
    try:
        res = run_basic_checks(u)
        return u, res
    except: return u, {"category_scores": {"SEO": 50}, "metrics": {"error": "Fetch Fail"}}

# ------------------------------------------------------------------------------
# 4. Routes (Fixed logout 404 and metrics 500)
# ------------------------------------------------------------------------------
@app.get("/")
async def index(request: Request, user: Optional[User] = Depends(get_current_user)):
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.post("/audit/open")
async def audit_open(request: Request, user: Optional[User] = Depends(get_current_user)):
    form = await request.form()
    url, res = _perform_real_audit(str(form.get("url", "")))
    cat_scores = {k: int(v) for k, v in res["category_scores"].items()}
    score = compute_overall(cat_scores)
    
    # Graphical Data Prepared
    radar_labels = list(cat_scores.keys())
    radar_values = list(cat_scores.values())

    return templates.TemplateResponse("audit_detail_open.html", {
        "request": request, "user": user, "website": {"url": url},
        "audit": {
            "health_score": int(score), "grade": grade_from_score(score),
            "category_scores": [{"name": k, "score": v} for k, v in cat_scores.items()],
            "exec_summary": summarize_200_words(url, cat_scores, res.get("top_issues", [])),
            "metrics": _present_metrics(res.get("metrics", {})), # FIXED 500 ERROR
            "competitor_comparison": [{"category": k, "target": v, "gap": v-80} for k, v in cat_scores.items()]
        },
        "chart": {"radar_labels": radar_labels, "radar_values": radar_values}
    })

@app.get("/auth/logout") # FIXED 404 ERROR
async def logout():
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie("session_token")
    return resp

@app.get("/auth/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    if not user: return RedirectResponse("/auth/login", status_code=303)
    audits = db.query(Audit).filter(Audit.user_id == user.id).order_by(Audit.created_at.desc()).limit(10).all()
    trend_labels = [a.created_at.strftime("%d %b") for a in reversed(audits)]
    trend_values = [a.health_score for a in reversed(audits)]
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user, "trend": {"labels": trend_labels, "values": trend_values},
        "websites": db.query(Website).filter(Website.user_id == user.id).all()
    })

# BackgroundTasks Fix (No Depends)
@app.post("/auth/register")
async def register_post(background_tasks: BackgroundTasks, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    u = User(email=email, password_hash=hash_password(password), verified=False); db.add(u); db.commit(); db.refresh(u)
    token = create_token({"uid": u.id, "email": u.email})
    background_tasks.add_task(send_verification_email, u.email, token)
    return RedirectResponse("/auth/login?check_email=1", status_code=303)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
