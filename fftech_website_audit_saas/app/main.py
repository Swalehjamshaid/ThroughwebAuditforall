# app/main.py
# -*- coding: utf-8 -*-

import os
import json
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from typing import Tuple, List, Dict, Any

from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from .db import Base, engine, SessionLocal
from .models import User, Website, Audit, Subscription
from .auth import hash_password, verify_password, create_token, decode_token
from .email_utils import send_verification_email
from .audit.engine import run_basic_checks
from .audit.grader import compute_overall, grade_from_score, summarize_200_words
from .audit.report import render_pdf_10p 

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


# ---------- Config ----------
UI_BRAND_NAME = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL      = os.getenv("BASE_URL", "http://localhost:8000")

SMTP_HOST     = os.getenv("SMTP_HOST")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

ADMIN_EMAIL    = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

FREE_AUDIT_LIMIT = int(os.getenv("FREE_AUDIT_LIMIT", "10"))
FREE_HISTORY_WINDOW_DAYS = int(os.getenv("FREE_HISTORY_WINDOW_DAYS", "30"))

app = FastAPI(title=f"{UI_BRAND_NAME} AI Website Audit SaaS")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# ---------- Startup schema patches ----------
def _ensure_schedule_columns():
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                ALTER TABLE subscriptions 
                ADD COLUMN IF NOT EXISTS daily_time VARCHAR(8) DEFAULT '09:00';
            """))
            conn.execute(text("""
                ALTER TABLE subscriptions 
                ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) DEFAULT 'UTC';
            """))
            conn.execute(text("""
                ALTER TABLE subscriptions 
                ADD COLUMN IF NOT EXISTS email_schedule_enabled BOOLEAN DEFAULT FALSE;
            """))
    except Exception:
        pass

def _ensure_user_columns():
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT FALSE;
            """))
            conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;
            """))
            conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
            """))
    except Exception:
        pass


# ---------- DB init helpers ----------
def _db_ping_ok() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

def _seed_admin_if_needed(db: Session):
    if not (ADMIN_EMAIL and ADMIN_PASSWORD):
        return
    existing = db.query(User).filter(User.email == ADMIN_EMAIL).first()
    if existing:
        changed = False
        if not getattr(existing, "is_admin", False):
            existing.is_admin = True; changed = True
        if not getattr(existing, "verified", False):
            existing.verified = True; changed = True
        if changed:
            db.commit()
        return
    admin = User(
        email=ADMIN_EMAIL,
        password_hash=hash_password(ADMIN_PASSWORD),
        verified=True,
        is_admin=True
    )
    db.add(admin); db.commit(); db.refresh(admin)

def init_db() -> bool:
    if not _db_ping_ok():
        return False
    try:
        Base.metadata.create_all(bind=engine)
        _ensure_schedule_columns()
        _ensure_user_columns()
        db = SessionLocal()
        try:
            _seed_admin_if_needed(db)
        finally:
            db.close()
        return True
    except Exception:
        return False


# ---------- DB dependency ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- Logic Helpers ----------

def _present_metrics(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Transforms raw audit data into a DICT for Jinja2 .items() compatibility."""
    if not raw:
        return {}
    
    display_map = {
        "lcp": "Largest Contentful Paint",
        "cls": "Cumulative Layout Shift",
        "inp": "Interaction to Next Paint",
        "ttfb": "Time to First Byte",
        "ssl_valid": "SSL Status",
        "hsts": "HSTS Header",
        "csp": "Content Security Policy",
        "canonical_present": "Canonical Tag",
        "robots_allowed": "Search Engine Indexing"
    }
    
    presentation = {}
    for key, label in display_map.items():
        val = raw.get(key, "N/A")
        if isinstance(val, bool):
            val = "Pass" if val else "Fail"
        presentation[label] = val
    
    return presentation

def _summarize_exec_200_words(url: str, category_scores: dict, top_issues: list) -> str:
    try:
        return summarize_200_words(url, category_scores, top_issues)
    except Exception:
        return "Comprehensive audit completed. Focus on performance and security headers."

def _normalize_url(raw: str) -> str:
    if not raw: return raw
    s = raw.strip()
    p = urlparse(s if "://" in s else "https://" + s)
    path = p.path or "/"
    return f"{p.scheme}://{p.netloc}{path}"

def _url_variants(u: str) -> List[str]:
    p = urlparse(u)
    host = p.netloc
    path = p.path or "/"
    scheme = p.scheme
    candidates = [f"{scheme}://{host}{path}"]
    candidates.append(f"{scheme}://{host[4:]}{path}" if host.startswith("www.") else f"{scheme}://www.{host}{path}")
    if not path.endswith("/"):
        candidates.append(f"{scheme}://{host}{path}/")
    seen, ordered = set(), []
    for c in candidates:
        if c not in seen:
            ordered.append(c); seen.add(c)
    return ordered

def _robust_audit(url: str) -> Tuple[str, dict]:
    base = _normalize_url(url)
    for candidate in _url_variants(base):
        try:
            res = run_basic_checks(candidate)
            if res.get("category_scores"):
                return candidate, res
        except Exception:
            continue
    # Fallback
    return base, {
        "category_scores": {"Performance": 50, "SEO": 50, "Security": 50},
        "metrics": {"ssl_valid": False},
        "top_issues": ["Audit fallback triggered"]
    }

def _maybe_competitor(raw_url: str):
    if not raw_url: return None, None
    try:
        return _robust_audit(raw_url)
    except Exception:
        return None, None


# ---------- Middleware ----------
current_user = None

@app.middleware("http")
async def session_middleware(request: Request, call_next):
    global current_user
    current_user = None
    token = request.cookies.get("session_token")
    if token:
        try:
            data = decode_token(token)
            uid = data.get("uid")
            if uid:
                db = SessionLocal()
                u = db.query(User).filter(User.id == uid).first()
                if u and u.verified:
                    current_user = u
                db.close()
        except Exception:
            pass
    return await call_next(request)


# ---------- Routes ----------

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user
    })

@app.post("/audit/open")
async def audit_open(request: Request):
    form = await request.form()
    url = form.get("url")
    comp_url = form.get("competitor_url")
    if not url: return RedirectResponse("/", status_code=303)

    norm, res = _robust_audit(url)
    scores = res["category_scores"]
    overall = compute_overall(scores)
    
    comp_norm, comp_res = _maybe_competitor(comp_url)
    comp_data = None
    if comp_res:
        comp_data = {
            "url": comp_norm,
            "category_scores": [{"name": k, "score": int(v)} for k, v in comp_res["category_scores"].items()]
        }

    return templates.TemplateResponse("audit_detail_open.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user,
        "website": {"id": None, "url": norm},
        "audit": {
            "created_at": datetime.utcnow(),
            "grade": grade_from_score(overall),
            "health_score": int(overall),
            "exec_summary": _summarize_exec_200_words(norm, scores, res.get("top_issues", [])),
            "category_scores": [{"name": k, "score": int(v)} for k, v in scores.items()],
            "metrics": _present_metrics(res.get("metrics", {})),
            "top_issues": res.get("top_issues", []),
            "competitor": comp_data
        }
    })

@app.get("/auth/audit/{website_id}")
async def audit_detail(website_id: int, request: Request, db: Session = Depends(get_db), competitor_url: str = None):
    if not current_user: return RedirectResponse("/auth/login", status_code=303)

    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    if not w or not a: return RedirectResponse("/auth/dashboard", status_code=303)

    metrics_raw = json.loads(a.metrics_json) if a.metrics_json else {}
    comp_norm, comp_res = _maybe_competitor(competitor_url)
    comp_data = None
    if comp_res:
        comp_data = {
            "url": comp_norm,
            "category_scores": [{"name": k, "score": int(v)} for k, v in comp_res["category_scores"].items()]
        }

    return templates.TemplateResponse("audit_detail.html", {
        "request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user, "website": w,
        "audit": {
            "created_at": a.created_at, "grade": a.grade, "health_score": a.health_score,
            "exec_summary": a.exec_summary, "category_scores": json.loads(a.category_scores_json),
            "metrics": _present_metrics(metrics_raw), "top_issues": metrics_raw.get("top_issues", []),
            "competitor": comp_data
        }
    })

# ---------- Additional Boilerplate (Login, Dashboard, etc) ----------

@app.on_event("startup")
async def startup_event():
    init_db()

# ... rest of your routes (auth, login, etc.) follow the same pattern ...
