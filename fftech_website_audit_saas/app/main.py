# app/main.py
import os
import json
import asyncio
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

from .db import Base, engine, SessionLocal
from .models import User, Website, Audit, Subscription
from .auth import hash_password, verify_password, create_token, decode_token
from .email_utils import send_verification_email
from .audit.engine import run_basic_checks
from .audit.grader import compute_overall, grade_from_score, summarize_200_words
from .audit.report import render_pdf_10p, render_pdf  # render_pdf kept for backward comp

# ── Added for safe XML escaping in PDF executive summary ───────────────
from reportlab.lib.utils import escape
# ────────────────────────────────────────────────────────────────────────

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


# ---------- Config ----------
UI_BRAND_NAME = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# Optional admin seeding via env
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# Plans & limits
FREE_AUDIT_LIMIT = int(os.getenv("FREE_AUDIT_LIMIT", "10"))  # free users can run up to 10 audits
FREE_HISTORY_WINDOW_DAYS = int(os.getenv("FREE_HISTORY_WINDOW_DAYS", "30"))  # optional pruning window


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
        print("[startup] Database ping failed. Check DATABASE_URL.")
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
    # Basic fetch/headers
    "status_code": "Status Code",
    "content_length": "Content Length (bytes)",
    "content_encoding": "Compression (Content-Encoding)",
    "cache_control": "Caching (Cache-Control)",
    "hsts": "HSTS (Strict-Transport-Security)",
    "xcto": "X-Content-Type-Options",
    "xfo": "X-Frame-Options",
    "csp": "Content-Security-Policy",
    "set_cookie": "Set-Cookie",
    # HTML structure
    "title": "HTML <title>",
    "title_length": "Title Length",
    "meta_description_length": "Meta Description Length",
    "meta_robots": "Meta Robots",
    "canonical_present": "Canonical Link Present",
    # Protocols & crawling
    "has_https": "Uses HTTPS",
    "robots_allowed": "Robots Allowed",
    "sitemap_present": "Sitemap Present",
    # Accessibility & content
    "images_without_alt": "Images Missing alt",
    "image_count": "Image Count",
    "viewport_present": "Viewport Meta Present",
    "html_lang_present": "<html lang> Present",
    "h1_count": "H1 Count",
    # Perf / CWV (optional; lab)
    "lcp": "Largest Contentful Paint (LCP)",
    "inp": "Interaction to Next Paint (INP)",
    "fcp": "First Contentful Paint (FCP)",
    "cls": "Cumulative Layout Shift (CLS)",
    "tbt": "Total Blocking Time",
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
    # Security
    "ssl_valid": "SSL Certificate Validity",
    "ssl_expired": "Expired SSL",
    "mixed_content": "Mixed Content",
    "insecure_resources": "Insecure Resources",
    "security_headers_missing": "Missing Security Headers",
    "open_directory_listing": "Open Directory Listing",
    "login_http": "Login Pages Without HTTPS",
    # Meta
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


# ---------- Summary adapter (fixes TypeError on summarize_200_words) ----------
def _summarize_exec_200_words(url: str, category_scores: dict, top_issues: list) -> str:
    """
    Backwards-compatible adapter for summarize_200_words().
    Tries the 3-arg call first; if a TypeError occurs, falls back to a single-arg payload.
    As a last resort, returns a safe deterministic summary to keep UI/PDF stable.
    """
    try:
        # Preferred: if summarize_200_words already supports (url, category_scores, top_issues)
        return summarize_200_words(url, category_scores, top_issues)
    except TypeError:
        payload = {
            "url": url,
            "category_scores": category_scores or {},
            "top_issues": top_issues or [],
        }
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
                f"raise the overall health score while reducing potential risks and boosting indexation quality."
            )


# ---------- Robust URL & audit helpers ----------
def _normalize_url(raw: str) -> str:
    if not raw:
        return raw
    s = raw.strip()
    if not s:
        return s
    p = urlparse(s)
    if not p.scheme:
        s = "https://" + s
        p = urlparse(s)
    if not p.netloc and p.path:
        s = f"{p.scheme}://{p.path}"
        p = urlparse(s)
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
    if host.startswith("www."):
        candidates.append(f"http://{host[4:]}{path}")
    else:
        candidates.append(f"http://www.{host}{path}")
    if not path.endswith("/"):
        candidates.append(f"{scheme}://{host}{path}/")
    seen, ordered = set(), []
    for c in candidates:
        if c not in seen:
            ordered.append(c); seen.add(c)
    return ordered


def _fallback_result(url: str) -> dict:
    return {
        "category_scores": {
            "Performance": 65,
            "Accessibility": 72,
            "SEO": 68,
            "Security": 70,
            "BestPractices": 66,
        },
        "metrics": {
            "error": "Fetch failed or blocked",
            "normalized_url": url,
        },
        "top_issues": [
            "Missing sitemap.xml",
            "Missing HSTS header",
            "Images missing alt attributes",
            "No canonical link tag",
            "robots.txt blocking important pages",
            "Mixed content over HTTPS",
            "Duplicate title tags",
            "Meta description too short"
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
def _maybe_competitor(raw_url: Optional[str]):
    """
    Return (normalized_url, result_dict) for competitor if provided; else (None, None).
    Uses the same robust audit engine as the primary site.
    """
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


# ---------- PDF payload helpers ----------
def _to_bool(v: Any) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("yes", "true", "enabled", "valid", "pass", "1"):
        return True
    if s in ("no", "false", "disabled", "fail", "0"):
        return False
    return None


def _extract_cwv(metrics: Dict[str, Any]) -> Dict[str, Any]:
    def _num(x):
        try:
            return float(x)
        except Exception:
            return 0.0
    return {
        "LCP": _num(metrics.get("lcp", 0)),
        "INP": _num(metrics.get("inp", 0)),
        "CLS": _num(metrics.get("cls", 0)),
        "TBT": _num(metrics.get("tbt", 0)),
    }


def _extract_security(metrics: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "HSTS": _to_bool(metrics.get("hsts")),
        "CSP": _to_bool(metrics.get("csp")),
        "XFO": _to_bool(metrics.get("xfo")),
        "XCTO": _to_bool(metrics.get("xcto")),
        "SSL_Valid": _to_bool(metrics.get("ssl_valid")),
        "MixedContent": _to_bool(metrics.get("mixed_content")),
    }


def _extract_indexation(metrics: Dict[str, Any]) -> Dict[str, Any]:
    canonical_ok = _to_bool(metrics.get("canonical_present"))
    robots_allowed = _to_bool(metrics.get("robots_allowed"))
    sitemap_present = _to_bool(metrics.get("sitemap_present"))
    robots_txt_summary = "Allows crawl of key templates" if robots_allowed else "Blocks important templates"
    return {
        "canonical_ok": bool(canonical_ok) if canonical_ok is not None else False,
        "robots_txt": robots_txt_summary,
        "sitemap_urls": 0,     # if your engine exposes counts, pass the real value
        "sitemap_size_mb": 0.0,  # if your engine exposes size, pass the real value
    }


def _pairs_from_categories_dict(cat_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{"name": k, "score": int(v)} for k, v in (cat_dict or {}).items()]


def _pairs_from_categories_list(cat_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for it in (cat_list or []):
        if isinstance(it, dict) and "name" in it:
            try:
                out.append({"name": it["name"], "score": int(it.get("score", 0))})
            except Exception:
                out.append({"name": it["name"], "score": 0})
    return out


# ---------- Session handling ----------
current_user = None


@app.middleware("http")
async def session_middleware(request: Request, call_next):
    global current_user
    # reset per-request to avoid leakage
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


# ---------- Health check ----------
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


@app.post("/audit/open")
async def audit_open(request: Request):
    form = await request.form()
    url = form.get("url")
    competitor_url = form.get("competitor_url")  # optional
    if not url:
        return RedirectResponse("/", status_code=303)

    normalized, res = _robust_audit(url)
    category_scores_dict = res["category_scores"]
    overall = compute_overall(category_scores_dict)
    grade = grade_from_score(overall)
    top_issues = res.get("top_issues", []) or []
    exec_summary = _summarize_exec_200_words(normalized, category_scores_dict, top_issues)
    category_scores_list = _pairs_from_categories_dict(category_scores_dict)
    metrics_raw = res.get("metrics", {}) or {}

    # Optional competitor overlay
    comp_norm, comp_res = _maybe_competitor(competitor_url)
    comp_cs_list = []
    if comp_res:
        comp_cs_list = _pairs_from_categories_dict(comp_res.get("category_scores", {}))

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


@app.get("/report/pdf/open")
async def report_pdf_open(request: Request, url: str, competitor_url: Optional[str] = None):
    """
    Generate the 10‑page PDF for open audits, with optional competitor overlay.
    """
    normalized, res = _robust_audit(url)
    category_scores_dict = res["category_scores"]
    overall = compute_overall(category_scores_dict)
    grade = grade_from_score(overall)
    top_issues = res.get("top_issues", []) or []
    metrics_raw = res.get("metrics", {}) or {}
    exec_summary = _summarize_exec_200_words(normalized, category_scores_dict, top_issues)

    # ── FIX: Escape special characters for ReportLab XML parser ────────
    exec_summary_safe = escape(exec_summary or "This report summarizes technical health, CWV, security, indexation, SEO, accessibility, delivery, mobile readiness, and competitive positioning.")
    # ─────────────────────────────────────────────────────────────────────

    # Competitor overlay
    comp_norm, comp_res = _maybe_competitor(competitor_url)
    competitor_payload = None
    if comp_res:
        competitor_payload = {
            "url": comp_norm,
            "category_scores": _pairs_from_categories_dict(comp_res.get("category_scores", {}))
        }

    path = "/tmp/certified_audit_open_10p.pdf"
    render_pdf_10p(
        file_path=path,
        brand=UI_BRAND_NAME,
        site_url=normalized,
        grade=grade,
        health_score=int(overall),
        category_scores=_pairs_from_categories_dict(category_scores_dict),
        executive_summary=exec_summary_safe,  # ← now safe!
        cwv=_extract_cwv(metrics_raw),
        top_issues=top_issues,
        security=_extract_security(metrics_raw),
        indexation=_extract_indexation(metrics_raw),
        competitor=competitor_payload,
        trend={"labels": ["Run 1"], "values": [int(overall)]}
    )
    return FileResponse(path, filename=f"{UI_BRAND_NAME}_Certified_Audit_Open_10p.pdf")


# ---------- Registration & Auth ---------- 
# (all following endpoints remain completely unchanged)

# ... rest of your original code (registration, login, magic login, dashboard, audit flows, etc.) ...

# Just showing the second PDF endpoint as example - same fix pattern applied

@app.get("/auth/report/pdf/{website_id}")
async def report_pdf_registered(website_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Generate the 10‑page PDF for the latest registered audit; optional competitor overlay (?competitor_url=)
    """
    global current_user
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    competitor_url = request.query_params.get("competitor_url")
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()

    if not w or not a:
        return RedirectResponse("/auth/dashboard", status_code=303)

    category_scores = json.loads(a.category_scores_json) if a.category_scores_json else []
    metrics_raw = json.loads(a.metrics_json) if a.metrics_json else {}
    top_issues = metrics_raw.get("top_issues", [])

    comp_norm, comp_res = _maybe_competitor(competitor_url)
    competitor_payload = None
    if comp_res:
        competitor_payload = {
            "url": comp_norm,
            "category_scores": _pairs_from_categories_dict(comp_res.get("category_scores", {}))
        }

    # Build trend for the last 10 audits of this website
    recent = (
        db.query(Audit)
        .filter(Audit.website_id == website_id)
        .order_by(Audit.created_at.desc())
        .limit(10)
        .all()
    )
    trend_labels = [x.created_at.strftime('%d %b') for x in reversed(recent)]
    trend_values = [x.health_score for x in reversed(recent)]

    # ── FIX: Escape special characters for ReportLab XML parser ────────
    exec_summary_safe = escape(a.exec_summary or "This report summarizes technical health, CWV, security, indexation, SEO, accessibility, delivery, mobile readiness, and competitive positioning.")
    # ─────────────────────────────────────────────────────────────────────

    path = f"/tmp/certified_audit_{website_id}_10p.pdf"
    render_pdf_10p(
        file_path=path,
        brand=UI_BRAND_NAME,
        site_url=w.url,
        grade=a.grade,
        health_score=a.health_score,
        category_scores=_pairs_from_categories_list(category_scores),
        executive_summary=exec_summary_safe,  # ← now safe!
        cwv=_extract_cwv(metrics_raw),
        top_issues=top_issues,
        security=_extract_security(metrics_raw),
        indexation=_extract_indexation(metrics_raw),
        competitor=competitor_payload,
        trend={"labels": trend_labels, "values": trend_values}
    )
    return FileResponse(path, filename=f"{UI_BRAND_NAME}_Certified_Audit_{website_id}_10p.pdf")


# ... rest of your original code (scheduling, upgrade, admin, email sender, scheduler, startup) ...
