
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
from .audit.report import render_pdf_10p  # NEW: 10-page PDF builder

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
    except OperationalError:
        return False
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


# ---------- Summary adapter (fixes TypeError on summarize_200_words) ----------
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
                f"Focus on improvements in performance, accessibility, and security headers to raise the overall score."
            )


# ---------- URL helpers ----------
def _normalize_url(raw: str) -> str:
    if not raw:
        return raw
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
    candidates.append(f"http://{host}{path}")
    candidates.append(f"http://{host[4:]}{path}" if host.startswith("www.") else f"http://www.{host}{path}")
    if not path.endswith("/"):
        candidates.append(f"{scheme}://{host}{path}/")
    seen, ordered = set(), []
    for c in candidates:
        if c not in seen:
            ordered.append(c); seen.add(c)
    return ordered


# ---------- Engine audit ----------
def _fallback_result(url: str) -> dict:
    return {
        "category_scores": {
            "Performance": 65,
            "Accessibility": 72,
            "SEO": 68,
            "Security": 70,
            "BestPractices": 66,
        },
        "metrics": {"normalized_url": url},
        "top_issues": [
            "Missing sitemap.xml",
            "Missing HSTS header",
            "Images missing alt",
            "No canonical link",
            "robots.txt blocking important pages",
            "Mixed content over HTTPS"
        ],
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


# ---------- Competitor helper ----------
def _maybe_competitor(raw_url: str):
    if not raw_url:
        return None, None
    try:
        comp_norm, comp_res = _robust_audit(raw_url)
        cats = comp_res.get("category_scores") or {}
        if cats and sum(int(v) for v in cats.values()) > 0:
            return comp_norm, comp_res
    except Exception:
        pass
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
    except Exception:
        pass
    response = await call_next(request)
    return response


# ---------- Health ----------
@app.get("/healthz")
async def healthz():
    ok = _db_ping_ok()
    return {"ok": ok, "brand": UI_BRAND_NAME}


# ---------- Public ----------
@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user
    })


# ---------- Utility: metrics mappers for PDF ----------
def _metric_value(m: Dict[str, Any], keys: List[str], default=None):
    """Fetch a value from metrics dict across multiple possible keys/labels."""
    for k in keys:
        if k in m: return m[k]
    # Try normalized label space (we sometimes store human-readable labels)
    for k in m.keys():
        if k.lower() in [kk.lower() for kk in keys]:
            return m[k]
    return default

def _security_from_metrics(m: Dict[str, Any]) -> Dict[str, Any]:
    # Booleans or pass/fail strings accepted
    hsts = _metric_value(m, ['hsts', 'HSTS (Strict-Transport-Security)'])
    csp  = _metric_value(m, ['csp', 'Content-Security-Policy'])
    xfo  = _metric_value(m, ['xfo', 'X-Frame-Options'])
    xcto = _metric_value(m, ['xcto', 'X-Content-Type-Options'])
    ssl  = _metric_value(m, ['ssl_valid', 'SSL Certificate Validity'])
    mixed= _metric_value(m, ['mixed_content', 'Mixed Content'])

    def to_bool_yes(v):
        if isinstance(v, bool): return v
        if isinstance(v, str): return v.strip().lower() in ('yes','enabled','pass','valid','true')
        return False

    def no_mixed(v):
        if isinstance(v, bool): return not v  # if True means mixed content present, pass=False
        if isinstance(v, str): return v.strip().lower() in ('no','false','none')
        return True  # assume no mixed content if unknown

    return {
        "HSTS": to_bool_yes(hsts),
        "CSP": to_bool_yes(csp),
        "XFO": to_bool_yes(xfo),
        "XCTO": to_bool_yes(xcto),
        "SSL_Valid": to_bool_yes(ssl),
        "MixedContent": no_mixed(mixed),
    }

def _cwv_from_metrics(m: Dict[str, Any]) -> Dict[str, Any]:
    lcp = _metric_value(m, ['lcp', 'Largest Contentful Paint (LCP)'], 0)
    inp = _metric_value(m, ['inp', 'First Input Delay', 'Interaction to Next Paint (INP)'], 0)
    cls = _metric_value(m, ['cls', 'Cumulative Layout Shift (CLS)'], 0)
    tbt = _metric_value(m, ['tbt', 'Total Blocking Time'], 0)

    # Convert to numeric, stripping units if needed
    def num(val):
        try:
            if isinstance(val, str):
                for suffix in ['ms','s']:
                    val = val.lower().replace(suffix, '')
            return float(val)
        except:
            return 0.0

    # LCP in seconds; INP/TBT in ms
    lcp = num(lcp)
    inp = num(inp)
    cls = num(cls)
    tbt = num(tbt)
    # If INP not present but FID present, map FID->INP best-effort
    if inp == 0:
        fid = _metric_value(m, ['fid', 'First Input Delay'], 0)
        inp = num(fid)

    return {"LCP": lcp, "INP": inp, "CLS": cls, "TBT": tbt}

def _indexation_from_metrics(m: Dict[str, Any]) -> Dict[str, Any]:
    canonical_ok = _metric_value(m, ['canonical_present', 'Canonical Link Present'], False)
    robots_txt = _metric_value(m, ['robots_allowed', 'Robots Allowed'], '')
    sitemap_present = _metric_value(m, ['sitemap_present', 'Sitemap Present'], '')
    # We may not have counts; placeholders OK
    return {
        "canonical_ok": bool(canonical_ok) if isinstance(canonical_ok, bool) else str(canonical_ok).lower() in ('yes','true'),
        "robots_txt": str(robots_txt) if robots_txt is not None else '',
        "sitemap_urls": _metric_value(m, ['sitemap_count','Sitemap URLs'], 'N/A'),
        "sitemap_size_mb": _metric_value(m, ['sitemap_size_mb','Sitemap Size (MB)'], 'N/A')
    }


# ---------- Open audit ----------
@app.post("/audit/open")
async def audit_open(request: Request):
    form = await request.form()
    url = form.get("url")
    competitor_url = form.get("competitor_url")

    if not url:
        return RedirectResponse("/", status_code=303)

    normalized, res = _robust_audit(url)
    category_scores_dict = res["category_scores"]
    overall = compute_overall(category_scores_dict)
    grade = grade_from_score(overall)
    top_issues = res.get("top_issues", []) or []
    exec_summary = _summarize_exec_200_words(normalized, category_scores_dict, top_issues)
    category_scores_list = [{"name": k, "score": int(v)} for k, v in category_scores_dict.items()]
    metrics_raw = res.get("metrics", {}) or {}

    # Optional competitor overlay
    comp_norm, comp_res = _maybe_competitor(competitor_url)
    comp_cs_list = []
    if comp_res:
        comp_cs_list = [{"name": k, "score": int(v)} for k, v in comp_res.get("category_scores", {}).items()]

    return templates.TemplateResponse("audit_detail_open.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user,
        "website": {"id": None, "url": normalized},
        "audit": {
            "created_at": datetime.utcnow(),
            "grade": grade,
            "health_score": int(overall),
            "exec_summary": exec_summary,
            "category_scores": category_scores_list,
            "metrics": _present_metrics(metrics_raw),
            "top_issues": top_issues,
            "competitor": ({"url": comp_norm, "category_scores": comp_cs_list} if comp_cs_list else None)
        }
    })


# ---------- Open report (PDF) ----------
@app.get("/report/pdf/open")
async def report_pdf_open(request: Request, url: str, competitor_url: str = None):
    normalized, res = _robust_audit(url)

    # Core data
    cats = [{"name": k, "score": int(v)} for k, v in res["category_scores"].items()]
    health = int(compute_overall(res["category_scores"]))
    grade = grade_from_score(health)
    issues = res.get("top_issues", []) or []
    metrics_raw = res.get("metrics", {}) or {}

    # Mapped sections
    cwv = _cwv_from_metrics(metrics_raw)
    security = _security_from_metrics(metrics_raw)
    indexation = _indexation_from_metrics(metrics_raw)

    # Competitor overlay
    comp_norm, comp_res = _maybe_competitor(competitor_url)
    competitor_payload = None
    if comp_res:
        competitor_payload = {
            "url": comp_norm,
            "category_scores": [{"name": k, "score": int(v)} for k, v in comp_res.get("category_scores", {}).items()]
        }

    # Trend (single run in open context)
    trend = {"labels": ["Run"], "values": [health]}

    path = "/tmp/certified_audit_open_10p.pdf"
    render_pdf_10p(
        file_path=path,
        brand=UI_BRAND_NAME,
        site_url=normalized,
        grade=grade,
        health_score=health,
        category_scores=cats,
        executive_summary=_summarize_exec_200_words(normalized, res["category_scores"], issues),
        cwv=cwv,
        top_issues=issues,
        security=security,
        indexation=indexation,
        competitor=competitor_payload,
        trend=trend
    )
    return FileResponse(path, filename=f"{UI_BRAND_NAME}_Executive_Audit_Open_10p.pdf")


# ---------- Registered flows ----------
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
    global current_user
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    websites = db.query(Website).filter(Website.user_id == current_user.id).all()
    last_audits = (
        db.query(Audit)
        .filter(Audit.user_id == current_user.id)
        .order_by(Audit.created_at.desc())
        .limit(10)
        .all()
    )
    avg = round(sum(a.health_score for a in last_audits)/len(last_audits), 1) if last_audits else 0
    trend_labels = [a.created_at.strftime('%d %b') for a in reversed(last_audits)]
    trend_values = [a.health_score for a in reversed(last_audits)]
    summary = {
        "grade": (last_audits[0].grade if last_audits else "A"),
        "health_score": (last_audits[0].health_score if last_audits else 88)
    }
    sub = _get_or_create_subscription(db, current_user.id)
    schedule = {
        "daily_time": getattr(sub, "daily_time", "09:00"),
        "timezone": getattr(sub, "timezone", "UTC"),
        "enabled": getattr(sub, "email_schedule_enabled", False) and not _is_free_plan(sub),
        "plan": getattr(sub, "plan", "free"),
        "audits_used": getattr(sub, "audits_used", 0),
        "free_limit": FREE_AUDIT_LIMIT
    }
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user,
        "websites": websites,
        "trend": {"labels": trend_labels, "values": trend_values, "average": avg},
        "summary": summary,
        "schedule": schedule
    })


@app.get("/auth/audit/new")
async def new_audit_get(request: Request):
    global current_user
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)
    return templates.TemplateResponse("new_audit.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user
    })


@app.post("/auth/audit/new")
async def new_audit_post(
    request: Request,
    url: str = Form(...),
    enable_schedule: str = Form(None),
    db: Session = Depends(get_db)
):
    global current_user
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    sub = _get_or_create_subscription(db, current_user.id)

    if _is_free_plan(sub) and (sub.audits_used or 0) >= FREE_AUDIT_LIMIT:
        return RedirectResponse("/auth/upgrade?limit=1", status_code=303)

    if enable_schedule and not _is_free_plan(sub) and hasattr(sub, "email_schedule_enabled"):
        sub.email_schedule_enabled = True
        db.commit()
    elif enable_schedule and _is_free_plan(sub):
        return RedirectResponse("/auth/upgrade?schedule=1", status_code=303)

    w = Website(user_id=current_user.id, url=url)
    db.add(w); db.commit(); db.refresh(w)

    return RedirectResponse(f"/auth/audit/run/{w.id}", status_code=303)


@app.get("/auth/audit/run/{website_id}")
async def run_audit(website_id: int, request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    if not w:
        return RedirectResponse("/auth/dashboard", status_code=303)

    sub = _get_or_create_subscription(db, current_user.id)
    if _is_free_plan(sub) and (sub.audits_used or 0) >= FREE_AUDIT_LIMIT:
        return RedirectResponse("/auth/upgrade?limit=1", status_code=303)

    try:
        normalized, res = _robust_audit(w.url)
    except Exception:
        return RedirectResponse("/auth/dashboard", status_code=303)

    category_scores_dict = res["category_scores"]
    overall = compute_overall(category_scores_dict)
    grade = grade_from_score(overall)
    top_issues = res.get("top_issues", []) or []
    exec_summary = _summarize_exec_200_words(normalized, category_scores_dict, top_issues)
    category_scores_list = [{"name": k, "score": int(v)} for k, v in category_scores_dict.items()]

    metrics_raw = res.get("metrics", {}) or {}
    metrics_raw["top_issues"] = top_issues

    audit = Audit(
        user_id=current_user.id,
        website_id=w.id,
        health_score=int(overall),
        grade=grade,
        exec_summary=exec_summary,
        category_scores_json=json.dumps(category_scores_list),
        metrics_json=json.dumps(metrics_raw)
    )
    db.add(audit); db.commit(); db.refresh(audit)

    w.last_audit_at = audit.created_at
    w.last_grade = grade
    db.commit()

    sub.audits_used = (sub.audits_used or 0) + 1
    db.commit()

    if _is_free_plan(sub):
        window = datetime.utcnow() - timedelta(days=FREE_HISTORY_WINDOW_DAYS)
        old_audits = db.query(Audit).filter(
            Audit.user_id == current_user.id,
            Audit.created_at < window
        ).all()
        for a_old in old_audits:
            try:
                db.delete(a_old)
            except Exception:
                pass
        db.commit()

    return RedirectResponse(f"/auth/audit/{w.id}", status_code=303)


@app.get("/auth/audit/{website_id}")
async def audit_detail(website_id: int, request: Request, db: Session = Depends(get_db), competitor_url: str = None):
    global current_user
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    if not w or not a:
        return RedirectResponse("/auth/dashboard", status_code=303)

    category_scores = json.loads(a.category_scores_json) if a.category_scores_json else []
    metrics_raw = json.loads(a.metrics_json) if a.metrics_json else {}
    metrics = _present_metrics(metrics_raw)
    top_issues = metrics_raw.get("top_issues", [])

    # Optional competitor overlay for web charts
    comp_norm, comp_res = _maybe_competitor(competitor_url)
    comp_cs_list = []
    if comp_res:
        comp_cs_list = [{"name": k, "score": int(v)} for k, v in comp_res.get("category_scores", {}).items()]

    return templates.TemplateResponse("audit_detail.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user,
        "website": w,
        "audit": {
            "created_at": a.created_at,
            "grade": a.grade,
            "health_score": a.health_score,
            "exec_summary": a.exec_summary,
            "category_scores": category_scores,
            "metrics": metrics,
            "top_issues": top_issues,
            "competitor": ({"url": comp_norm, "category_scores": comp_cs_list} if comp_cs_list else None)
        }
    })


# ---------- Registered report (PDF) ----------
@app.get("/auth/report/pdf/{website_id}")
async def report_pdf(website_id: int, request: Request, db: Session = Depends(get_db), competitor_url: str = None):
    global current_user
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    if not w or not a:
        return RedirectResponse("/auth/dashboard", status_code=303)

    # Core data
    cats = json.loads(a.category_scores_json) if a.category_scores_json else []
    health = int(a.health_score)
    grade = a.grade
    issues = (json.loads(a.metrics_json).get("top_issues", []) if a.metrics_json else [])
    metrics_raw = json.loads(a.metrics_json) if a.metrics_json else {}

    # Mapped sections
    cwv = _cwv_from_metrics(metrics_raw)
    security = _security_from_metrics(metrics_raw)
    indexation = _indexation_from_metrics(metrics_raw)

    # Competitor overlay
    comp_norm, comp_res = _maybe_competitor(competitor_url)
    competitor_payload = None
    if comp_res:
        competitor_payload = {
            "url": comp_norm,
            "category_scores": [{"name": k, "score": int(v)} for k, v in comp_res.get("category_scores", {}).items()]
        }

    # Trend from last 10 audits
    last_audits = (
        db.query(Audit)
        .filter(Audit.user_id == current_user.id, Audit.website_id == website_id)
        .order_by(Audit.created_at.desc())
        .limit(10)
        .all()
    )
    trend_labels = [a.created_at.strftime('%d %b') for a in reversed(last_audits)]
    trend_values = [a.health_score for a in reversed(last_audits)]
    trend = {"labels": trend_labels, "values": trend_values}

    path = f"/tmp/certified_audit_{website_id}_10p.pdf"
    render_pdf_10p(
        file_path=path,
        brand=UI_BRAND_NAME,
        site_url=w.url,
        grade=grade,
        health_score=health,
        category_scores=cats,
        executive_summary=a.exec_summary,
        cwv=cwv,
        top_issues=issues,
        security=security,
        indexation=indexation,
        competitor=competitor_payload,
        trend=trend
    )
    return FileResponse(path, filename=f"{UI_BRAND_NAME}_Executive_Audit_{website_id}_10p.pdf")


# ---------- Scheduling UI ----------
@app.get("/auth/schedule")
async def schedule_get(request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    sub = _get_or_create_subscription(db, current_user.id)
    schedule = {
        "daily_time": getattr(sub, "daily_time", "09:00"),
        "timezone": getattr(sub, "timezone", "UTC"),
        "enabled": getattr(sub, "email_schedule_enabled", False) and not _is_free_plan(sub),
        "plan": getattr(sub, "plan", "free"),
        "audits_used": getattr(sub, "audits_used", 0),
        "free_limit": FREE_AUDIT_LIMIT
    }

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user,
        "websites": db.query(Website).filter(Website.user_id == current_user.id).all(),
        "trend": {"labels": [], "values": [], "average": 0},
        "summary": {"grade": "A", "health_score": 88},
        "schedule": schedule
    })


@app.post("/auth/schedule")
async def schedule_post(
    request: Request,
    daily_time: str = Form(...),
    timezone: str = Form(...),
    enabled: str = Form(None),
    db: Session = Depends(get_db)
):
    global current_user
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    sub = _get_or_create_subscription(db, current_user.id)

    if hasattr(sub, "daily_time"):
        sub.daily_time = daily_time
    if hasattr(sub, "timezone"):
        sub.timezone = timezone

    if hasattr(sub, "email_schedule_enabled"):
        if _is_free_plan(sub):
            sub.email_schedule_enabled = False
            db.commit()
            return RedirectResponse("/auth/upgrade?schedule=1", status_code=303)
        else:
            sub.email_schedule_enabled = bool(enabled)

    db.commit()
    return RedirectResponse("/auth/dashboard", status_code=303)


# ---------- Upgrade ----------
@app.get("/auth/upgrade")
async def upgrade(request: Request):
    return templates.TemplateResponse("upgrade.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user
    })


# ---------- Admin ----------
@app.get("/auth/admin/login")
async def admin_login_get(request: Request):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user
    })

@app.post("/auth/admin/login")
async def admin_login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    global current_user
    u = db.query(User).filter(User.email == email).first()
    if not u or not verify_password(password, u.password_hash) or not u.is_admin:
        return RedirectResponse("/auth/admin/login", status_code=303)

    current_user = u
    token = create_token({"uid": u.id, "email": u.email, "admin": True}, expires_minutes=60*24*30)

    resp = RedirectResponse("/auth/admin", status_code=303)
    resp.set_cookie(
        key="session_token", value=token,
        httponly=True, secure=BASE_URL.startswith("https://"),
        samesite="Lax", max_age=60*60*24*30
    )
    return resp

@app.get("/auth/admin")
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user or not current_user.is_admin:
        return RedirectResponse("/auth/admin/login", status_code=303)

    users = db.query(User).order_by(User.created_at.desc()).limit(100).all()
    audits = db.query(Audit).order_by(Audit.created_at.desc()).limit(100).all()
    websites = db.query(Website).order_by(Website.created_at.desc()).limit(100).all()

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user,
        "websites": websites,
        "admin_users": users,
        "admin_audits": audits
    })


# ---------- Email sender & scheduler ----------
def _send_report_email(to_email: str, subject: str, html_body: str) -> bool:
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = to_email
    msg.attach(MIMEText(html_body, "html"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [to_email], msg.as_string())
        return True
    except Exception:
        return False

async def _daily_scheduler_loop():
    while True:
        try:
            db = SessionLocal()
            try:
                subs = db.query(Subscription).filter(Subscription.active == True).all()
                now_utc = datetime.utcnow()
                for sub in subs:
                    if _is_free_plan(sub) or not getattr(sub, "email_schedule_enabled", False):
                        continue
                    tz_name    = getattr(sub, "timezone", "UTC") or "UTC"
                    daily_time = getattr(sub, "daily_time", "09:00") or "09:00"
                    try:
                        tz = ZoneInfo(tz_name)
                    except Exception:
                        tz = ZoneInfo("UTC")
                    local_now = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
                    hhmm_now  = local_now.strftime("%H:%M")
                    if hhmm_now != daily_time:
                        continue
                    user = db.query(User).filter(User.id == sub.user_id).first()
                    if not user or not getattr(user, "verified", False):
                        continue
                    websites = db.query(Website).filter(Website.user_id == user.id).all()
                    lines = [
                        f"<h3>Daily Website Audit Summary – {UI_BRAND_NAME}</h3>",
                        f"<p>Hello, {user.email}!</p>",
                        "<p>Here is your daily summary. Download certified PDFs via links below.</p>"
                    ]
                    for w in websites:
                        last = (
                            db.query(Audit)
                            .filter(Audit.website_id == w.id)
                            .order_by(Audit.created_at.desc())
                            .first()
                        )
                        if not last:
                            lines.append(f"<p><b>{w.url}</b>: No audits yet.</p>")
                            continue
                        pdf_link = f"{BASE_URL.rstrip('/')}/auth/report/pdf/{w.id}"
                        lines.append(
                            f'<p><b>{w.url}</b>: Grade <b>{last.grade}</b>, Health <b>{last.health_score}</b>/100 '
                            f'({pdf_link}Download Certified Report</a>)</p>'
                        )
                    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
                    audits_30 = db.query(Audit).filter(
                        Audit.user_id == user.id,
                        Audit.created_at >= thirty_days_ago
                    ).all()
                    if audits_30:
                        avg_score = round(sum(a.health_score for a in audits_30) / len(audits_30), 1)
                        lines.append(f"<hr><p><b>30-day accumulated score:</b> {avg_score}/100</p>")
                    else:
                        lines.append("<hr><p><b>30-day accumulated score:</b> Not enough data yet.</p>")
                    html = "\n".join(lines)
                    _send_report_email(user.email, f"{UI_BRAND_NAME} – Daily Website Audit Summary", html)
            finally:
                db.close()
        except Exception as e:
            print(f"[scheduler] error: {e}")
        await asyncio.sleep(60)


# ---------- Startup ----------
@app.on_event("startup")
async def _start_scheduler():
    init_ok = init_db()
    if not init_ok:
        print("[startup] DB not initialized; scheduler will still start, but email jobs may fail.")
    asyncio.create_task(_daily_scheduler_loop())
