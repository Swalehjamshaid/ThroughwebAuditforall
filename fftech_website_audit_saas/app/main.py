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
# Configuration helpers (Preserved)
# ------------------------------------------------------------------------------
def _env(*keys: str) -> Optional[str]:
    """Return the first non-empty env var among given keys."""
    for k in keys:
        v = os.getenv(k)
        if v is not None and v.strip() != "":
            return v.strip()
    return None

def _looks_placeholder(value: Optional[str]) -> bool:
    """Heuristics to detect placeholder values (treated as missing)."""
    if not value:
        return True
    v = value.strip().lower()
    return v in {"changeme", "password", "example", "placeholder"} or "real_16_char_app_password" in v

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
UI_BRAND_NAME: str = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")

SMTP_HOST: Optional[str] = _env("SMTP_HOST", "MAIL_HOST")
SMTP_PORT: int = int(_env("SMTP_PORT", "MAIL_PORT") or "587")
SMTP_USER: Optional[str] = _env("SMTP_USER", "SMTP_USERNAME", "EMAIL_USER")
SMTP_PASSWORD: Optional[str] = _env("SMTP_PASSWORD", "SMTP_PASS", "SMTP_API_KEY")

MAGIC_EMAIL_ENABLED: bool = os.getenv("MAGIC_EMAIL_ENABLED", "true").lower() == "true"
SMTP_TIMEOUT_SEC: float = float(os.getenv("SMTP_TIMEOUT_SEC", "10.0"))
SMTP_MAX_RETRIES: int = int(os.getenv("SMTP_MAX_RETRIES", "2"))
SMTP_BACKOFF_BASE_SEC: float = float(os.getenv("SMTP_BACKOFF_BASE_SEC", "1.0"))

ADMIN_EMAIL: Optional[str] = os.getenv("ADMIN_EMAIL", "roy.jamshaid@gmail.com")
COMPETITOR_BASELINE_JSON: Optional[str] = os.getenv(
    "COMPETITOR_BASELINE_JSON",
    '{"Performance": 82, "Accessibility": 88, "SEO": 85, "Security": 90, "BestPractices": 84}',
)

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
logger = logging.getLogger("fftech.app")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

# ------------------------------------------------------------------------------
# FastAPI app, static & templates
# ------------------------------------------------------------------------------
app = FastAPI(title=f"{UI_BRAND_NAME} — Website Audit SaaS")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Context Processor for Global Template Variables
def inject_globals(request: Request):
    return {
        "datetime": datetime,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "year": datetime.utcnow().year,
        "now": datetime.utcnow(),
    }
templates.context_processors.append(inject_globals)

# ------------------------------------------------------------------------------
# DB schema initialization & patches
# ------------------------------------------------------------------------------
Base.metadata.create_all(bind=engine)

def _run_db_patches():
    try:
        with engine.connect() as conn:
            # Subscriptions
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS daily_time VARCHAR(8) DEFAULT '09:00';"))
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) DEFAULT 'UTC';"))
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS email_schedule_enabled BOOLEAN DEFAULT FALSE;"))
            # Users
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT FALSE;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();"))
            # Auto-verify Admin
            if ADMIN_EMAIL:
                conn.execute(text("UPDATE users SET verified = True, is_admin = True WHERE email = :email"), {"email": ADMIN_EMAIL})
            conn.commit()
            logger.info("Database patches applied successfully.")
    except Exception as e:
        logger.warning(f"DB Patch failed: {e}")

_run_db_patches()

# ------------------------------------------------------------------------------
# Dependencies
# ------------------------------------------------------------------------------
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try: yield db
    finally: db.close()

async def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    try:
        token = request.cookies.get("session_token")
        if not token: return None
        data = decode_token(token)
        uid = data.get("uid")
        user = db.query(User).filter(User.id == uid).first()
        if user and getattr(user, "verified", False):
            return user
        return None
    except: return None

# ------------------------------------------------------------------------------
# Metric Presenters & Competitor Comparison
# ------------------------------------------------------------------------------
METRIC_LABELS: Dict[str, str] = {
    "status_code": "Status Code", "has_https": "Uses HTTPS", "content_length": "Page Size",
    "title": "HTML <title>", "h1_count": "H1 Count", "viewport_present": "Responsive",
    "error": "Fetch Error"
}

def _present_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in (metrics or {}).items():
        label = METRIC_LABELS.get(k, k.replace("_", " ").title())
        out[label] = "Yes" if v is True else ("No" if v is False else v)
    return out

def _get_competitor_comparison(target_scores: Dict[str, int]) -> Iterable[Dict[str, Any]]:
    try:
        baseline = json.loads(COMPETITOR_BASELINE_JSON or "{}")
    except:
        baseline = {"Performance": 80, "Accessibility": 80, "SEO": 80, "Security": 80, "BestPractices": 80}
    
    return [{
        "category": cat, "target": int(score), "competitor": baseline.get(cat, 80),
        "gap": int(score) - baseline.get(cat, 80),
        "status": "Lead" if int(score) >= baseline.get(cat, 80) else "Lag"
    } for cat, score in target_scores.items()]

# ------------------------------------------------------------------------------
# Audit Logic
# ------------------------------------------------------------------------------
def _normalize_url(raw: str) -> str:
    if not raw: return raw
    s = raw.strip()
    p = urlparse(s)
    if not p.scheme: s = "https://" + s; p = urlparse(s)
    return f"{p.scheme}://{p.netloc}{p.path or '/'}"

def _robust_audit(url: str) -> Tuple[str, Dict[str, Any]]:
    base = _normalize_url(url)
    try:
        res = run_basic_checks(base)
        if res.get("category_scores"): return base, res
    except: pass
    return base, {"category_scores": {"Performance": 60, "SEO": 60}, "metrics": {"error": "Heuristic fallback"}}

# ------------------------------------------------------------------------------
# SMTP Resilience logic
# ------------------------------------------------------------------------------
def _smtp_send_with_retries(msg: MIMEMultipart, to_email: str) -> bool:
    if not MAGIC_EMAIL_ENABLED or not _smtp_config_ok(): return False
    delay = SMTP_BACKOFF_BASE_SEC
    for attempt in range(1, SMTP_MAX_RETRIES + 2):
        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SEC) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, [to_email], msg.as_string())
            return True
        except Exception as e:
            logger.warning(f"SMTP attempt {attempt} failed: {e}")
            if attempt <= SMTP_MAX_RETRIES: time.sleep(delay); delay *= 2
    return False

def _send_magic_login_email(to_email: str, token: str) -> None:
    link = f"{BASE_URL.rstrip('/')}/auth/magic?token={token}"
    html = f"<h3>Magic Login</h3><p><a href='{link}'>{link}</a></p>"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{UI_BRAND_NAME} Magic Login"; msg["From"] = SMTP_USER; msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))
    if not _smtp_send_with_retries(msg, to_email):
        logger.warning(f"Failed to send magic mail to {to_email}. Log: {link}")

# ------------------------------------------------------------------------------
# Routes - AUTH (Fixes the 405 Method Not Allowed)
# ------------------------------------------------------------------------------
@app.get("/")
async def index(request: Request, user: Optional[User] = Depends(get_current_user)):
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.get("/auth/register") # FIX: GET route for register form
async def register_get(request: Request, user: Optional[User] = Depends(get_current_user)):
    return templates.TemplateResponse("register.html", {"request": request, "user": user})

@app.post("/auth/register")
async def register_post(background_tasks: BackgroundTasks, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == email).first():
        return RedirectResponse("/auth/login?exists=1", status_code=303)
    u = User(email=email, password_hash=hash_password(password), verified=False)
    db.add(u); db.commit(); db.refresh(u)
    token = create_token({"uid": u.id, "email": u.email})
    background_tasks.add_task(send_verification_email, u.email, token)
    return RedirectResponse("/auth/login?check_email=1", status_code=303)

@app.post("/auth/magic/request")
async def magic_request(background_tasks: BackgroundTasks, email: str = Form(...), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == email).first()
    status = "skip"
    if u and u.verified:
        token = create_token({"uid": u.id, "email": u.email, "type": "magic"}, expires_minutes=15)
        background_tasks.add_task(_send_magic_login_email, u.email, token)
        status = "queued"
    return RedirectResponse(f"/auth/login?magic_sent=1&smtp={status}", status_code=303)

@app.get("/auth/logout")
async def logout():
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie("session_token")
    return resp

# ------------------------------------------------------------------------------
# Routes - AUDIT (Fixes the UndefinedError metrics)
# ------------------------------------------------------------------------------
@app.post("/audit/open")
async def audit_open(request: Request, user: Optional[User] = Depends(get_current_user)):
    form = await request.form()
    url, res = _robust_audit(str(form.get("url", "")))
    cat_scores = {k: int(v) for k, v in res["category_scores"].items()}
    score = compute_overall(cat_scores)
    
    return templates.TemplateResponse("audit_detail_open.html", {
        "request": request, "user": user, "website": {"url": url},
        "audit": {
            "health_score": int(score), "grade": grade_from_score(score),
            "category_scores": [{"name": k, "score": v} for k, v in cat_scores.items()],
            "exec_summary": summarize_200_words(url, cat_scores, res.get("top_issues", [])),
            "metrics": _present_metrics(res.get("metrics", {})), # FIXED: metrics added
            "competitor_comparison": _get_competitor_comparison(cat_scores)
        },
        "chart": {"radar_labels": list(cat_scores.keys()), "radar_values": list(cat_scores.values())}
    })

@app.get("/auth/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    if not user: return RedirectResponse("/auth/login", status_code=303)
    audits = db.query(Audit).filter(Audit.user_id == user.id).order_by(Audit.created_at.desc()).limit(12).all()
    trend_labels = [a.created_at.strftime("%d %b") for a in reversed(audits)]
    trend_values = [a.health_score for a in reversed(audits)]
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user, 
        "websites": db.query(Website).filter(Website.user_id == user.id).all(),
        "trend": {"labels": trend_labels, "values": trend_values}
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
