from __future__ import annotations

import os
import json
import asyncio
import logging
import smtplib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, Generator, Iterable, Optional, Tuple
from urllib.parse import urlparse

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import FastAPI, Request, Form, Depends, Response
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
# Configuration
# ------------------------------------------------------------------------------
UI_BRAND_NAME: str = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")

SMTP_HOST: Optional[str] = os.getenv("SMTP_HOST")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: Optional[str] = os.getenv("SMTP_USER")
SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD")

ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "roy.jamshaid@gmail.com")
COMPETITOR_BASELINE_JSON: str = os.getenv(
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
# FastAPI setup
# ------------------------------------------------------------------------------
app = FastAPI(title=f"{UI_BRAND_NAME} — Website Audit SaaS")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# CORRECTED: Plural context_processors list for FastAPI/Starlette
def inject_globals(request: Request):
    return {
        "datetime": datetime,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "year": datetime.utcnow().year,
        "now": datetime.utcnow(),
    }
templates.context_processors.append(inject_globals)

# ------------------------------------------------------------------------------
# DB Initialization & SQL Patches
# ------------------------------------------------------------------------------
Base.metadata.create_all(bind=engine)

def _apply_startup_sql_patches():
    try:
        with engine.connect() as conn:
            # Subscription columns patch
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS daily_time VARCHAR(8) DEFAULT '09:00';"))
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) DEFAULT 'UTC';"))
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS email_schedule_enabled BOOLEAN DEFAULT FALSE;"))
            
            # User columns patch
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT FALSE;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();"))
            
            # Auto-Verify Roy's Admin Account (Requested Attribute)
            conn.execute(text("UPDATE users SET verified = True, is_admin = True WHERE email = :email"), {"email": ADMIN_EMAIL})
            
            conn.commit()
            logger.info("Startup SQL patches and admin auto-verification applied successfully.")
    except Exception as e:
        logger.warning("Startup SQL patch failed: %s", e)

_apply_startup_sql_patches()

# ------------------------------------------------------------------------------
# Dependencies
# ------------------------------------------------------------------------------
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    try:
        token = request.cookies.get("session_token")
        if not token: 
            return None
        data = decode_token(token)
        uid = data.get("uid")
        if not uid: 
            return None
        user = db.query(User).filter(User.id == uid).first()
        return user if (user and getattr(user, "verified", False)) else None
    except Exception:
        return None

# ------------------------------------------------------------------------------
# Metric Labels
# ------------------------------------------------------------------------------
METRIC_LABELS: Dict[str, str] = {
    "status_code": "Status Code",
    "content_length": "Content Length (bytes)",
    "content_encoding": "Compression (Content-Encoding)",
    "cache_control": "Caching (Cache-Control)",
    "hsts": "HSTS (Strict-Transport-Security)",
    "xcto": "X-Content-Type-Options",
    "xfo": "X-Frame-Options",
    "csp": "Content-Security-Policy",
    "set_cookie": "Set-Cookie",
    "title": "HTML <title>",
    "title_length": "Title Length",
    "meta_description_length": "Meta Description Length",
    "meta_robots": "Meta Robots",
    "canonical_present": "Canonical Link Present",
    "has_https": "Uses HTTPS",
    "robots_allowed": "Robots Allowed",
    "sitemap_present": "Sitemap Present",
    "images_without_alt": "Images Missing alt",
    "image_count": "Image Count",
    "viewport_present": "Viewport Meta Present",
    "html_lang_present": "<html lang> Present",
    "h1_count": "H1 Count",
    "normalized_url": "Normalized URL",
    "error": "Fetch Error",
}

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def _present_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in (metrics or {}).items():
        label = METRIC_LABELS.get(k, k.replace("_", " ").title())
        if isinstance(v, bool):
            v = "Yes" if v else "No"
        out[label] = v
    return out

def _get_competitor_comparison(target_scores: Dict[str, int]) -> Iterable[Dict[str, Any]]:
    try:
        baseline = json.loads(COMPETITOR_BASELINE_JSON)
    except Exception:
        baseline = {"Performance": 80, "Accessibility": 80, "SEO": 80, "Security": 80, "BestPractices": 80}
    
    comparison = []
    for cat, score in target_scores.items():
        comp_val = int(baseline.get(cat, 80))
        diff = int(score) - comp_val
        comparison.append({
            "category": cat,
            "target": int(score),
            "competitor": comp_val,
            "gap": diff,
            "status": "Lead" if diff >= 0 else "Lag"
        })
    return comparison

def _normalize_url(raw: str) -> str:
    if not raw: return raw
    s = raw.strip()
    p = urlparse(s)
    if not p.scheme:
        s = "https://" + s
        p = urlparse(s)
    path = p.path or "/"
    return f"{p.scheme}://{p.netloc}{path}"

def _url_variants(u: str) -> Iterable[str]:
    p = urlparse(u)
    host, path, scheme = p.netloc, p.path or "/", p.scheme
    candidates = [f"{scheme}://{host}{path}"]
    if host.startswith("www."): 
        candidates.append(f"{scheme}://{host[4:]}{path}")
    else: 
        candidates.append(f"{scheme}://www.{host}{path}")
    candidates.append(f"http://{host}{path}")
    seen, ordered = set(), []
    for c in candidates:
        if c not in seen: 
            ordered.append(c)
            seen.add(c)
    return ordered

def _fallback_result(url: str):
    return {
        "category_scores": {"Performance": 60, "SEO": 60, "Accessibility": 60, "Security": 60, "BestPractices": 60}, 
        "metrics": {"error": "Heuristic fallback", "normalized_url": url}, 
        "top_issues": ["Site accessibility check failed; using heuristic fallback."]
    }

def _robust_audit(url: str) -> Tuple[str, Dict[str, Any]]:
    base = _normalize_url(url)
    for candidate in _url_variants(base):
        try:
            res = run_basic_checks(candidate)
            if res.get("category_scores") and sum(int(v) for v in res["category_scores"].values()) > 0:
                return candidate, res
        except Exception: 
            continue
    return base, _fallback_result(base)

# ------------------------------------------------------------------------------
# Routes — Public
# ------------------------------------------------------------------------------
@app.get("/")
async def index(request: Request, user: Optional[User] = Depends(get_current_user)):
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.post("/audit/open")
async def audit_open(request: Request, user: Optional[User] = Depends(get_current_user)):
    form = await request.form()
    url = str(form.get("url", ""))
    if not url: return RedirectResponse("/", status_code=303)
    
    normalized, res = _robust_audit(url)
    cat_scores = {k: int(v) for k, v in res["category_scores"].items()}
    overall = compute_overall(cat_scores)
    grade = grade_from_score(overall)
    top_issues = res.get("top_issues", [])
    exec_summary = summarize_200_words(normalized, cat_scores, top_issues)
    
    return templates.TemplateResponse("audit_detail_open.html", {
        "request": request, 
        "user": user, 
        "website": {"id": None, "url": normalized},
        "audit": {
            "health_score": int(overall), 
            "grade": grade,
            "exec_summary": exec_summary,
            "category_scores": [{"name": k, "score": v} for k, v in cat_scores.items()],
            "metrics": _present_metrics(res.get("metrics", {})),
            "top_issues": top_issues,
            "competitor_comparison": list(_get_competitor_comparison(cat_scores))
        },
        "chart": {
            "radar_labels": list(cat_scores.keys()),
            "radar_values": list(cat_scores.values()),
            "health": int(overall),
            "trend_labels": [],
            "trend_values": []
        }
    })

@app.get("/report/pdf/open")
async def report_pdf_open(url: str):
    normalized, res = _robust_audit(url)
    cat_scores_dict = {k: int(v) for k, v in res["category_scores"].items()}
    cat_scores_list = [{"name": k, "score": v} for k, v in cat_scores_dict.items()]
    overall = compute_overall(cat_scores_dict)
    exec_summary = summarize_200_words(normalized, cat_scores_dict, res.get("top_issues", []))
    
    path = "/tmp/open_audit.pdf"
    render_pdf(path, UI_BRAND_NAME, normalized, grade_from_score(overall), int(overall), cat_scores_list, exec_summary)
    return FileResponse(path, filename=f"{UI_BRAND_NAME}_Audit.pdf")

# ------------------------------------------------------------------------------
# Routes — Auth & Magic Link
# ------------------------------------------------------------------------------
@app.get("/auth/login")
async def login_get(request: Request, user: Optional[User] = Depends(get_current_user)):
    return templates.TemplateResponse("login.html", {"request": request, "user": user})

@app.post("/auth/magic/request")
@app.post("/auth/magic/request/")
async def magic_request(email: str = Form(...), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == email).first()
    if u and getattr(u, "verified", False):
        token = create_token({"uid": u.id, "email": u.email, "type": "magic"}, expires_minutes=15)
        _send_magic_login_email(u.email, token)
    return RedirectResponse("/auth/login?magic_sent=1", status_code=303)

@app.get("/auth/magic")
async def magic_login(token: str, db: Session = Depends(get_db)):
    try:
        data = decode_token(token)
        if data.get("type") != "magic": 
            return RedirectResponse("/auth/login?error=1", status_code=303)
        u = db.query(User).filter(User.id == data["uid"]).first()
        if u and getattr(u, "verified", False):
            resp = RedirectResponse("/auth/dashboard", status_code=303)
            session_token = create_token({"uid": u.id, "email": u.email}, expires_minutes=43200)
            resp.set_cookie(key="session_token", value=session_token, httponly=True, secure=BASE_URL.startswith("https://"), samesite="Lax")
            return resp
    except Exception: 
        pass
    return RedirectResponse("/auth/login?error=1", status_code=303)

@app.get("/auth/dashboard")
async def dashboard(request: Request, user: Optional[User] = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user: return RedirectResponse("/auth/login", status_code=303)
    websites = db.query(Website).filter(Website.user_id == user.id).all()
    last_audits = db.query(Audit).filter(Audit.user_id == user.id).order_by(Audit.created_at.desc()).limit(10).all()
    
    avg = round(sum(a.health_score for a in last_audits) / len(last_audits), 1) if last_audits else 0
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user, "websites": websites,
        "trend": {
            "labels": [a.created_at.strftime("%d %b") for a in reversed(last_audits)], 
            "values": [a.health_score for a in reversed(last_audits)],
            "average": avg
        }
    })

@app.get("/auth/audit/{website_id}")
async def audit_detail(website_id: int, request: Request, user: Optional[User] = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user: return RedirectResponse("/auth/login", status_code=303)
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    if not w or not a: return RedirectResponse("/auth/dashboard", status_code=303)
    
    cat_scores = json.loads(a.category_scores_json)
    scores_dict = {item["name"]: item["score"] for item in cat_scores}
    
    return templates.TemplateResponse("audit_detail.html", {
        "request": request, "user": user, "website": w,
        "audit": {
            "created_at": a.created_at, "grade": a.grade, "health_score": a.health_score, "exec_summary": a.exec_summary, 
            "category_scores": cat_scores, "metrics": _present_metrics(json.loads(a.metrics_json)),
            "competitor_comparison": list(_get_competitor_comparison(scores_dict))
        },
        "chart": {
            "radar_labels": [i["name"] for i in cat_scores],
            "radar_values": [i["score"] for i in cat_scores],
            "health": a.health_score
        }
    })

@app.get("/auth/report/pdf/{website_id}")
async def report_pdf_auth(website_id: int, user: Optional[User] = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user: return RedirectResponse("/auth/login")
    a = db.query(Audit).filter(Audit.website_id == website_id, Audit.user_id == user.id).order_by(Audit.created_at.desc()).first()
    w = db.query(Website).filter(Website.id == website_id).first()
    if not a or not w: return RedirectResponse("/auth/dashboard")
    
    path = f"/tmp/audit_{website_id}.pdf"
    render_pdf(path, UI_BRAND_NAME, w.url, a.grade, a.health_score, json.loads(a.category_scores_json), a.exec_summary)
    return FileResponse(path, filename=f"Audit_{w.url}.pdf")

# ------------------------------------------------------------------------------
# Email Helpers & Background Scheduler
# ------------------------------------------------------------------------------
def _send_magic_login_email(to_email: str, token: str):
    login_link = f"{BASE_URL.rstrip('/')}/auth/magic?token={token}"
    msg = MIMEMultipart()
    msg["Subject"] = f"{UI_BRAND_NAME} Magic Login"
    msg["From"] = SMTP_USER
    msg["To"] = to_email
    msg.attach(MIMEText(f"Click here to log in securely: {login_link}", "plain"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [to_email], msg.as_string())
    except Exception as e: 
        logger.error("SMTP Error: %s", e)

async def _daily_scheduler_loop():
    while True:
        try:
            db = SessionLocal()
            # In a full implementation, query subscriptions here and send daily emails
            db.close()
        except Exception as e:
            logger.error("Scheduler error: %s", e)
        await asyncio.sleep(3600) 

@app.on_event("startup")
async def _start_scheduler():
    asyncio.create_task(_daily_scheduler_loop())

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, workers=1)

# Ensure metrics dictionary is accessible
METRIC_LABELS: Dict[str, str] = {
    "status_code": "Status Code", "content_length": "Content Length", "has_https": "HTTPS Secure",
    "title": "Page Title", "h1_count": "H1 Tags", "error": "Technical Errors"
}
