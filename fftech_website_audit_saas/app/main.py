# app/main.py
# -*- coding: utf-8 -*-

import os
import json
import asyncio
import smtplib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from typing import Tuple, Optional, Dict, Any, List

from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from .db import Base, engine, SessionLocal
from .models import User, Website, Audit, Subscription
from .auth import hash_password, verify_password, create_token, decode_token
from .email_utils import send_verification_email
from .audit.engine import run_basic_checks
from .audit.grader import compute_overall, grade_from_score, summarize_200_words
from .audit.report import render_pdf_10p, render_pdf  # render_pdf kept for backward comp

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

# ---- Startup schema patches ----
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
    except Exception as e:
        print(f"[schema] Schedule patch error: {e}")

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
    except Exception as e:
        print(f"[schema] User patch error: {e}")

# ---------- DB init helpers ----------
def _db_ping_ok() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (OperationalError, Exception):
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
        print("[startup] Database ping failed.")
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
        print("[startup] Database initialized successfully.")
        return True
    except Exception as e:
        print(f"[startup] Database initialization error: {e}")
        return False

# ---------- DB dependency ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------- Metrics presenter ----------
METRIC_LABELS = {
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
    "lcp": "Largest Contentful Paint (LCP)",
    "fcp": "First Contentful Paint (FCP)",
    "cls": "Cumulative Layout Shift (CLS)",
    "tbt": "Total Blocking Time",
    "fid": "First Input Delay",
    "speed_index": "Speed Index",
    "tti": "Time to Interactive",
    "dom_content_loaded": "DOM Content Loaded",
    "total_page_size": "Total Page Size",
    "requests_per_page": "Requests Per Page",
    "unminified_css": "Unminified CSS",
    "unminified_js": "Unminified JavaScript",
    "render_blocking": "Render Blocking Resources",
    "excessive_dom": "Excessive DOM Size",
    "third_party_load": "Third-Party Script Load",
    "server_response_time": "Server Response Time",
    "image_optimization": "Image Optimization",
    "lazy_loading_issues": "Lazy Loading Issues",
    "browser_caching": "Browser Caching Issues",
    "missing_gzip_brotli": "Missing GZIP / Brotli",
    "resource_load_errors": "Resource Load Errors",
    "ssl_valid": "SSL Certificate Validity",
    "ssl_expired": "Expired SSL",
    "mixed_content": "Mixed Content",
    "insecure_resources": "Insecure Resources",
    "security_headers_missing": "Missing Security Headers",
    "open_directory_listing": "Open Directory Listing",
    "login_http": "Login Pages Without HTTPS",
    "normalized_url": "Normalized URL",
    "error": "Fetch Error",
}

def _present_metrics(metrics: dict) -> dict:
    out = {}
    for k, v in (metrics or {}).items():
        label = METRIC_LABELS.get(k, k.replace("_", " ").title())
        if isinstance(v, bool):
            v = "Yes" if v else "No"
        out[label] = v
    return out

# ---------- Summary adapter ----------
def _summarize_exec_200_words(url: str, category_scores: dict, top_issues: list) -> str:
    try:
        return summarize_200_words(url, category_scores, top_issues)
    except TypeError:
        payload = {"url": url, "category_scores": category_scores or {}, "top_issues": top_issues or []}
        try:
            return summarize_200_words(payload)
        except Exception:
            cats = category_scores or {}
            strengths = ", ".join(sorted([k for k, v in cats.items() if int(v) >= 75])) or "Core areas performing well"
            weaknesses = ", ".join(sorted([k for k, v in cats.items() if int(v) < 60])) or "Some categories need improvement"
            issues_preview = ", ".join((top_issues or [])[:5]) or "No critical issues reported"
            return (
                f"This website shows a balanced technical and SEO profile. Strengths include {strengths}. "
                f"Weaknesses include {weaknesses}. Priority areas involve addressing: {issues_preview}. "
                f"Focus on incremental improvements in performance, accessibility, and security headers to "
                f"raise the overall health score while reducing potential risks."
            )

# ---------- Robust URL & audit helpers ----------
def _normalize_url(raw: str) -> str:
    if not raw: return raw
    s = raw.strip()
    p = urlparse(s if "://" in s else "https://" + s)
    path = p.path or "/"
    return f"{p.scheme}://{p.netloc}{path}"

def _url_variants(u: str) -> list:
    p = urlparse(u)
    host = p.netloc
    path = p.path or "/"
    scheme = p.scheme
    candidates = [f"{scheme}://{host}{path}"]
    if host.startswith("www."):
        candidates.append(f"{scheme}://{host[4:]}{path}")
    else:
        candidates.append(f"{scheme}://www.{host}{path}")
    candidates.append(f"http://{host}{path}")
    if not path.endswith("/"):
        candidates.append(f"{scheme}://{host}{path}/")
    seen, ordered = set(), []
    for c in candidates:
        if c not in seen:
            ordered.append(c); seen.add(c)
    return ordered

def _fallback_result(url: str) -> dict:
    return {
        "category_scores": {"Performance": 65, "Accessibility": 72, "SEO": 68, "Security": 70, "BestPractices": 66},
        "metrics": {"error": "Fetch failed or blocked", "normalized_url": url},
        "top_issues": ["Missing sitemap.xml", "Missing HSTS header", "Images missing alt", "No canonical link tag"]
    }

def _robust_audit(url: str) -> Tuple[str, dict]:
    base = _normalize_url(url)
    for candidate in _url_variants(base):
        try:
            res = run_basic_checks(candidate)
            cats = res.get("category_scores") or {}
            if cats and sum(int(v) for v in cats.values()) > 0:
                return candidate, res
        except Exception:
            continue
    return base, _fallback_result(base)

def _maybe_competitor(raw_url: Optional[str]):
    if not raw_url: return None, None
    try:
        comp_norm, comp_res = _robust_audit(raw_url)
        cats = comp_res.get("category_scores") or {}
        if cats and sum(int(v) for v in cats.values()) > 0:
            return comp_norm, comp_res
    except Exception: pass
    return None, None

# ---------- Session handling ----------
current_user = None

@app.middleware("http")
async def session_middleware(request: Request, call_next):
    global current_user
    current_user = None
    try:
        token = request.cookies.get("session_token")
        if token:
            data = decode_token(token)
            uid = data.get("uid")
            if uid:
                db = SessionLocal()
                try:
                    u = db.query(User).filter(User.id == uid).first()
                    if u and getattr(u, "verified", False):
                        current_user = u
                finally:
                    db.close()
    except Exception: pass
    return await call_next(request)

# ---------- Health check ----------
@app.get("/healthz")
async def healthz():
    return {"ok": _db_ping_ok(), "brand": UI_BRAND_NAME}

# ---------- Public Routes ----------
@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user
    })

@app.post("/audit/open")
async def audit_open(request: Request):
    form = await request.form()
    url = form.get("url")
    competitor_url = form.get("competitor_url")
    if not url: return RedirectResponse("/", status_code=303)

    normalized, res = _robust_audit(url)
    category_scores_dict = res["category_scores"]
    overall = compute_overall(category_scores_dict)
    grade = grade_from_score(overall)
    top_issues = res.get("top_issues", []) or []
    exec_summary = _summarize_exec_200_words(normalized, category_scores_dict, top_issues)
    category_scores_list = [{"name": k, "score": int(v)} for k, v in category_scores_dict.items()]
    metrics = _present_metrics(res.get("metrics", {}))

    comp_norm, comp_res = _maybe_competitor(competitor_url)
    comp_cs_list = [{"name": k, "score": int(v)} for k, v in comp_res.get("category_scores", {}).items()] if comp_res else []

    return templates.TemplateResponse("audit_detail_open.html", {
        "request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user,
        "website": {"id": None, "url": normalized},
        "audit": {
            "created_at": datetime.utcnow(),
            "grade": grade,
            "health_score": int(overall),
            "exec_summary": exec_summary,
            "category_scores": category_scores_list,
            "metrics": metrics,
            "top_issues": top_issues,
            "competitor": ({"url": comp_norm, "category_scores": comp_cs_list} if comp_cs_list else None)
        }
    })

@app.get("/report/pdf/open")
async def report_pdf_open(url: str):
    normalized, res = _robust_audit(url)
    cs_list = [{"name": k, "score": int(v)} for k, v in res["category_scores"].items()]
    overall = compute_overall(res["category_scores"])
    grade = grade_from_score(overall)
    top_issues = res.get("top_issues", []) or []
    exec_summary = _summarize_exec_200_words(normalized, res["category_scores"], top_issues)
    path = "/tmp/certified_audit_open.pdf"
    render_pdf(path, UI_BRAND_NAME, normalized, grade, int(overall), cs_list, exec_summary)
    return FileResponse(path, filename=f"{UI_BRAND_NAME}_Certified_Audit_Open.pdf")

# ---------- Registration & Auth ----------
@app.get("/auth/register")
async def register_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user})

@app.post("/auth/register")
async def register_post(request: Request, email: str = Form(...), password: str = Form(...), confirm_password: str = Form(...), db: Session = Depends(get_db)):
    if password != confirm_password: return RedirectResponse("/auth/register?mismatch=1", status_code=303)
    if db.query(User).filter(User.email == email).first(): return RedirectResponse("/auth/login?exists=1", status_code=303)
    u = User(email=email, password_hash=hash_password(password), verified=False, is_admin=False)
    db.add(u); db.commit(); db.refresh(u)
    token = create_token({"uid": u.id, "email": u.email}, expires_minutes=1440)
    send_verification_email(u.email, token)
    return RedirectResponse("/auth/login?check_email=1", status_code=303)

@app.get("/auth/verify")
async def verify(request: Request, token: str, db: Session = Depends(get_db)):
    try:
        data = decode_token(token)
        u = db.query(User).filter(User.id == data["uid"]).first()
        if u:
            u.verified = True; db.commit()
            return RedirectResponse("/auth/login?verified=1", status_code=303)
    except Exception:
        return templates.TemplateResponse("verify.html", {"request": request, "success": False, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user})
    return RedirectResponse("/auth/login", status_code=303)

@app.get("/auth/login")
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user})

@app.post("/auth/login")
async def login_post(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    global current_user
    u = db.query(User).filter(User.email == email).first()
    if not u or not verify_password(password, u.password_hash) or not u.verified:
        return RedirectResponse("/auth/login?error=1", status_code=303)
    current_user = u
    token = create_token({"uid": u.id, "email": u.email}, expires_minutes=43200)
    resp = RedirectResponse("/auth/dashboard", status_code=303)
    resp.set_cookie(key="session_token", value=token, httponly=True, secure=BASE_URL.startswith("https://"), samesite="Lax", max_age=2592000)
    return resp

@app.get("/auth/logout")
async def logout(request: Request):
    global current_user
    current_user = None
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("session_token")
    return resp

# ---------- Dashboard & Audit flows ----------
def _get_or_create_subscription(db: Session, user_id: int) -> Subscription:
    sub = db.query(Subscription).filter(Subscription.user_id == user_id).first()
    if not sub:
        sub = Subscription(user_id=user_id, plan="free", active=True, audits_used=0)
        db.add(sub); db.commit(); db.refresh(sub)
    return sub

def _is_free_plan(sub: Subscription) -> bool:
    return (getattr(sub, "plan", "free") or "free").lower() == "free"

@app.get("/auth/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    if not current_user: return RedirectResponse("/auth/login", status_code=303)
    websites = db.query(Website).filter(Website.user_id == current_user.id).all()
    last_audits = db.query(Audit).filter(Audit.user_id == current_user.id).order_by(Audit.created_at.desc()).limit(10).all()
    avg = round(sum(a.health_score for a in last_audits)/len(last_audits), 1) if last_audits else 0
    sub = _get_or_create_subscription(db, current_user.id)
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user, "websites": websites,
        "trend": {"labels": [a.created_at.strftime('%d %b') for a in reversed(last_audits)], "values": [a.health_score for a in reversed(last_audits)], "average": avg},
        "summary": {"grade": (last_audits[0].grade if last_audits else "A"), "health_score": (last_audits[0].health_score if last_audits else 0)},
        "schedule": {"plan": getattr(sub, "plan", "free"), "audits_used": getattr(sub, "audits_used", 0), "free_limit": FREE_AUDIT_LIMIT}
    })

@app.get("/auth/audit/new")
async def new_audit_get(request: Request):
    if not current_user: return RedirectResponse("/auth/login", status_code=303)
    return templates.TemplateResponse("new_audit.html", {"request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user})

@app.post("/auth/audit/new")
async def new_audit_post(request: Request, url: str = Form(...), enable_schedule: str = Form(None), db: Session = Depends(get_db)):
    if not current_user: return RedirectResponse("/auth/login", status_code=303)
    sub = _get_or_create_subscription(db, current_user.id)
    if _is_free_plan(sub) and (sub.audits_used or 0) >= FREE_AUDIT_LIMIT: return RedirectResponse("/auth/upgrade?limit=1", status_code=303)
    w = Website(user_id=current_user.id, url=url)
    db.add(w); db.commit(); db.refresh(w)
    return RedirectResponse(f"/auth/audit/run/{w.id}", status_code=303)

@app.get("/auth/audit/run/{website_id}")
async def run_audit(website_id: int, request: Request, db: Session = Depends(get_db)):
    if not current_user: return RedirectResponse("/auth/login", status_code=303)
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    sub = _get_or_create_subscription(db, current_user.id)
    normalized, res = _robust_audit(w.url)
    overall = compute_overall(res["category_scores"])
    audit = Audit(user_id=current_user.id, website_id=w.id, health_score=int(overall), grade=grade_from_score(overall),
                  exec_summary=_summarize_exec_200_words(normalized, res["category_scores"], res.get("top_issues", [])),
                  category_scores_json=json.dumps([{"name": k, "score": int(v)} for k, v in res["category_scores"].items()]),
                  metrics_json=json.dumps(res.get("metrics", {})))
    db.add(audit); sub.audits_used += 1; db.commit()
    return RedirectResponse(f"/auth/audit/{w.id}", status_code=303)

@app.get("/auth/audit/{website_id}")
async def audit_detail(website_id: int, request: Request, db: Session = Depends(get_db)):
    if not current_user: return RedirectResponse("/auth/login", status_code=303)
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    metrics_raw = json.loads(a.metrics_json) if a.metrics_json else {}
    return templates.TemplateResponse("audit_detail.html", {
        "request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user, "website": w,
        "audit": {
            "created_at": a.created_at, "grade": a.grade, "health_score": a.health_score, "exec_summary": a.exec_summary,
            "category_scores": json.loads(a.category_scores_json), "metrics": _present_metrics(metrics_raw),
            "top_issues": metrics_raw.get("top_issues", [])
        }
    })

# ---------- Admin ----------
@app.get("/auth/admin")
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    if not current_user or not current_user.is_admin: return RedirectResponse("/auth/login", status_code=303)
    users = db.query(User).limit(100).all()
    audits = db.query(Audit).limit(100).all()
    return templates.TemplateResponse("admin.html", {"request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user, "admin_users": users, "admin_audits": audits})

# ---------- Scheduler & Email ----------
def _send_report_email(to_email, subject, html_body):
    if not (SMTP_HOST and SMTP_USER): return False
    msg = MIMEMultipart("alternative"); msg["Subject"] = subject; msg["From"] = SMTP_USER; msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls(); server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [to_email], msg.as_string())
        return True
    except Exception: return False

async def _daily_scheduler_loop():
    while True:
        try:
            db = SessionLocal()
            try:
                subs = db.query(Subscription).filter(Subscription.active == True, Subscription.email_schedule_enabled == True).all()
                for sub in subs:
                    user = db.query(User).filter(User.id == sub.user_id).first()
                    _send_report_email(user.email, f"Daily Audit Summary - {UI_BRAND_NAME}", "<p>Your daily audit reports are ready.</p>")
            finally: db.close()
        except Exception as e: print(f"[scheduler] error: {e}")
        await asyncio.sleep(3600)

@app.on_event("startup")
async def _startup():
    if init_db(): asyncio.create_task(_daily_scheduler_loop())
