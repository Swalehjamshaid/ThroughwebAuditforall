
# app/main.py
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
from fastapi.background import BackgroundTasks
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

# Email behavior toggles & timeouts
MAGIC_EMAIL_ENABLED: bool = os.getenv("MAGIC_EMAIL_ENABLED", "true").lower() == "true"
SMTP_TIMEOUT_SEC: float = float(os.getenv("SMTP_TIMEOUT_SEC", "6.0"))
SMTP_MAX_RETRIES: int = int(os.getenv("SMTP_MAX_RETRIES", "2"))  # total attempts = 1 + retries
SMTP_BACKOFF_BASE_SEC: float = float(os.getenv("SMTP_BACKOFF_BASE_SEC", "1.0"))

ADMIN_EMAIL: Optional[str] = os.getenv("ADMIN_EMAIL")  # optional auto-verify admin
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
templates.env.globals.update(
    {
        "datetime": datetime,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "year": datetime.utcnow().year,
        "now": datetime.utcnow(),
    }
)

# ------------------------------------------------------------------------------
# DB schema initialization & patches
# ------------------------------------------------------------------------------
Base.metadata.create_all(bind=engine)


def _ensure_schedule_columns() -> None:
    """Ensure new schedule columns are present for subscriptions."""
    try:
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE subscriptions "
                "ADD COLUMN IF NOT EXISTS daily_time VARCHAR(8) DEFAULT '09:00';"
            ))
            conn.execute(text(
                "ALTER TABLE subscriptions "
                "ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) DEFAULT 'UTC';"
            ))
            conn.execute(text(
                "ALTER TABLE subscriptions "
                "ADD COLUMN IF NOT EXISTS email_schedule_enabled BOOLEAN DEFAULT FALSE;"
            ))
            conn.commit()
    except Exception as e:
        logger.warning("Schedule columns patch failed: %s", e)


def _ensure_user_columns() -> None:
    """Ensure additional columns for users are present."""
    try:
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT FALSE;"
            ))
            conn.execute(text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;"
            ))
            conn.execute(text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();"
            ))
            conn.commit()
    except Exception as e:
        logger.warning("User columns patch failed: %s", e)


def _auto_verify_admin() -> None:
    """Optionally auto-verify a specific admin email from env (for bootstrap)."""
    if not ADMIN_EMAIL:
        return
    try:
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE users SET verified = True, is_admin = True WHERE email = :email"),
                {"email": ADMIN_EMAIL},
            )
            conn.commit()
            logger.info("Auto-verified admin account: %s", ADMIN_EMAIL)
    except Exception as e:
        logger.warning("Auto verify admin failed: %s", e)


_ensure_schedule_columns()
_ensure_user_columns()
_auto_verify_admin()

# ------------------------------------------------------------------------------
# DB dependency & per-request user dependency
# ------------------------------------------------------------------------------
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """
    Resolve the current user per-request from the session cookie.
    Returns None if there is no valid/verified user.
    """
    try:
        token = request.cookies.get("session_token")
        if not token:
            return None
        data = decode_token(token)
        uid = data.get("uid")
        if not uid:
            return None
        user = db.query(User).filter(User.id == uid).first()
        if user and getattr(user, "verified", False):
            return user
        return None
    except Exception as e:
        logger.debug("get_current_user error: %s", e)
        return None


# ------------------------------------------------------------------------------
# Security headers middleware
# ------------------------------------------------------------------------------
@app.middleware("http")
async def security_headers(request: Request, call_next):
    """
    Adds a minimal set of security headers to every response.
    (Fine-tune for your domain & CSP if you need stricter policies.)
    """
    response: Response = await call_next(request)
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    return response


# ------------------------------------------------------------------------------
# Health & readiness
# ------------------------------------------------------------------------------
@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/ready")
def ready() -> JSONResponse:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return JSONResponse({"status": "ready"})
    except Exception as e:
        logger.error("Readiness DB check failed: %s", e)
        return JSONResponse({"status": "not-ready"}, status_code=503)


# ------------------------------------------------------------------------------
# Metric labels & presenters
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


def _present_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Convert raw metric keys/values to human-friendly labels and formats for UI."""
    out: Dict[str, Any] = {}
    for k, v in (metrics or {}).items():
        label = METRIC_LABELS.get(k, k.replace("_", " ").title())
        if isinstance(v, bool):
            v = "Yes" if v else "No"
        out[label] = v
    return out


# ------------------------------------------------------------------------------
# Competitor baseline comparison (UI helper)
# ------------------------------------------------------------------------------
def _get_competitor_comparison(target_scores: Dict[str, int]) -> Iterable[Dict[str, Any]]:
    """Compare target scores to a configurable competitor baseline."""
    try:
        baseline: Dict[str, int] = json.loads(COMPETITOR_BASELINE_JSON or "{}")
    except Exception:
        baseline = {"Performance": 80, "Accessibility": 80, "SEO": 80, "Security": 80, "BestPractices": 80}

    comparison = []
    for cat, score in target_scores.items():
        comp_val = int(baseline.get(cat, 80))
        diff = int(score) - comp_val
        comparison.append(
            {
                "category": cat,
                "target": int(score),
                "competitor": comp_val,
                "gap": diff,
                "status": "Lead" if diff >= 0 else "Lag",
            }
        )
    return comparison


# ------------------------------------------------------------------------------
# URL normalization & resilient audit
# ------------------------------------------------------------------------------
def _normalize_url(raw: str) -> str:
    if not raw:
        return raw
    s = raw.strip()
    p = urlparse(s)
    if not p.scheme:
        s = "https://" + s
        p = urlparse(s)
    if not p.netloc and p.path:
        s = f"{p.scheme}://{p.path}"
        p = urlparse(s)
    path = p.path or "/"
    return f"{p.scheme}://{p.netloc}{path}"


def _url_variants(u: str) -> Iterable[str]:
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
            ordered.append(c)
            seen.add(c)
    return ordered


def _fallback_result(url: str) -> Dict[str, Any]:
    return {
        "category_scores": {
            "Performance": 65,
            "Accessibility": 72,
            "SEO": 68,
            "Security": 70,
            "BestPractices": 66,
        },
        "metrics": {"error": "Fetch failed or blocked", "normalized_url": url},
        "top_issues": [
            "Fetch failed; using heuristic baseline.",
            "Verify URL is publicly accessible and not blocked by WAF/robots.",
        ],
    }


def _robust_audit(url: str) -> Tuple[str, Dict[str, Any]]:
    """Attempt multiple URL variants; return first successful result or fallback."""
    base = _normalize_url(url)
    for candidate in _url_variants(base):
        try:
            res = run_basic_checks(candidate)
            cats = res.get("category_scores") or {}
            if cats and sum(int(v) for v in cats.values()) > 0:
                return candidate, res
        except Exception as e:
            logger.debug("Variant failed (%s): %s", candidate, e)
            continue
    return base, _fallback_result(base)


# ------------------------------------------------------------------------------
# SMTP helpers (timeouts, retries, background-safe)
# ------------------------------------------------------------------------------
def _smtp_send_with_retries(msg: MIMEMultipart, to_email: str) -> bool:
    """
    Low-level SMTP send with connection timeout and bounded retries.
    Returns True on success, False otherwise.
    """
    if not MAGIC_EMAIL_ENABLED:
        logger.warning("SMTP disabled by config (MAGIC_EMAIL_ENABLED=false); skipping send to %s", to_email)
        return False

    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        logger.info("SMTP not fully configured; skip send to %s", to_email)
        return False

    delay = SMTP_BACKOFF_BASE_SEC
    attempts = SMTP_MAX_RETRIES + 1  # initial + retries
    for attempt in range(1, attempts + 1):
        try:
            logger.info("SMTP: connecting %s:%s as %s (attempt %d/%d)",
                        SMTP_HOST, SMTP_PORT, SMTP_USER, attempt, attempts)
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SEC) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(SMTP_USER, SMTP_PASSWORD)  # type: ignore[arg-type]
                server.sendmail(SMTP_USER, [to_email], msg.as_string())  # type: ignore[arg-type]
            logger.info("SMTP: sent email to %s", to_email)
            return True
        except (smtplib.SMTPException, OSError) as e:
            # Covers 'Network is unreachable', DNS issues, auth failures, etc.
            logger.warning("SMTP send failed to %s: %s", to_email, e)
            if attempt < attempts:
                # Exponential backoff (works in sync or async contexts)
                try:
                    loop = asyncio.get_running_loop()
                    # schedule sleep within running loop
                    async def _sleep():
                        await asyncio.sleep(delay)
                    # Run a nested task to sleep without blocking unrelated tasks
                    loop.run_until_complete(_sleep())  # type: ignore[attr-defined]
                except RuntimeError:
                    # No running loop -> do a blocking sleep
                    import time
                    time.sleep(delay)
                delay *= 2
                continue
            return False
        except Exception as e:
            logger.warning("Unexpected SMTP error to %s: %s", to_email, e)
            return False


def _send_magic_login_email(to_email: str, token: str) -> None:
    """
    Background task: build & send magic login email via SMTP.
    Non-blocking for the request path; logs link if sending is disabled or fails.
    """
    login_link = f"{BASE_URL.rstrip('/')}/auth/magic?token={token}"
    html_body = f"""
    <h3>{UI_BRAND_NAME} — Magic Login</h3>
    <p>Hello!</p>
    <p>Click the secure link below to log in:</p>
    <p><a href="{login_link}" target="_
    <p>This link will expire shortly. If you didn't request it, you can ignore this message.</p>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{UI_BRAND_NAME} — Magic Login Link"
    msg["From"] = SMTP_USER or ""
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    ok = _smtp_send_with_retries(msg, to_email)
    if not ok:
        # Graceful fallback: log the link so admins/devs can assist users
        logger.warning("Magic email delivery failed or disabled; link for %s: %s", to_email, login_link)


def _send_report_email(to_email: str, subject: str, html_body: str) -> bool:
    """
    Daily report email with the same timeout/retry protections.
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER or ""
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))
    return _smtp_send_with_retries(msg, to_email)


# ------------------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------------------
def _set_session_cookie(resp: Response, token: str, *, max_age_days: int = 30) -> None:
    """Set a secure, HTTP-only session cookie."""
    resp.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=BASE_URL.startswith("https://"),
        samesite="Lax",
        max_age=60 * 60 * 24 * max_age_days,
    )


# ------------------------------------------------------------------------------
# Routes — public
# ------------------------------------------------------------------------------
@app.get("/")
async def index(request: Request, user: Optional[User] = Depends(get_current_user)):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "user": user},
    )

# Legacy/bookmark alias to fix Railway 405 loops
@app.get("/login")
async def login_redirect():
    """
    Normalize legacy/bookmarked '/login' to the actual login page route.
    Prevents GET /login 405 errors in proxies/health checks.
    """
    return RedirectResponse("/auth/login", status_code=307)


@app.post("/audit/open")
async def audit_open(request: Request, user: Optional[User] = Depends(get_current_user)):
    form = await request.form()
    url = form.get("url")
    if not url:
        return RedirectResponse("/", status_code=303)

    normalized, res = _robust_audit(url)
    category_scores_dict: Dict[str, int] = {k: int(v) for k, v in (res["category_scores"] or {}).items()}
    overall = compute_overall(category_scores_dict)
    grade = grade_from_score(overall)
    top_issues = res.get("top_issues", [])
    exec_summary = summarize_200_words(normalized, category_scores_dict, top_issues)
    category_scores_list = [{"name": k, "score": int(v)} for k, v in category_scores_dict.items()]

    radar_labels = list(category_scores_dict.keys())
    radar_values = [int(v) for v in category_scores_dict.values()]

    return templates.TemplateResponse(
        "audit_detail_open.html",
        {
            "request": request,
            "user": user,
            "website": {"id": None, "url": normalized},
            "audit": {
                "created_at": datetime.utcnow(),
                "grade": grade,
                "health_score": int(overall),
                "exec_summary": exec_summary,
                "category_scores": category_scores_list,
                "metrics": _present_metrics(res.get("metrics", {})),
                "top_issues": top_issues,
                "competitor_comparison": list(_get_competitor_comparison(category_scores_dict)),
            },
            "chart": {
                "radar_labels": radar_labels,
                "radar_values": radar_values,
                "health": int(overall),
                "trend_labels": [],
                "trend_values": [],
            },
            "UI_BRAND_NAME": UI_BRAND_NAME,
        },
    )


@app.get("/report/pdf/open")
async def report_pdf_open(url: str):
    normalized, res = _robust_audit(url)
    category_scores_dict: Dict[str, int] = {k: int(v) for k, v in (res["category_scores"] or {}).items()}
    overall = compute_overall(category_scores_dict)
    grade = grade_from_score(overall)
    top_issues = res.get("top_issues", [])
    exec_summary = summarize_200_words(normalized, category_scores_dict, top_issues)

    path = "/tmp/certified_audit_open.pdf"
    render_pdf(
        path,
        UI_BRAND_NAME,
        normalized,
        grade,
        int(overall),
        [{"name": k, "score": int(v)} for k, v in category_scores_dict.items()],
        exec_summary,
    )
    return FileResponse(path, filename=f"{UI_BRAND_NAME}_Certified_Audit_Open.pdf")


# ------------------------------------------------------------------------------
# Registration & Auth
# ------------------------------------------------------------------------------
@app.get("/auth/register")
async def register_get(request: Request, user: Optional[User] = Depends(get_current_user)):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "user": user, "UI_BRAND_NAME": UI_BRAND_NAME},
    )


@app.post("/auth/register")
async def register_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None,  # <-- NO Depends(); FastAPI injects this automatically
):
    if password != confirm_password:
        return RedirectResponse("/auth/register?mismatch=1", status_code=303)

    if db.query(User).filter(User.email == email).first():
        return RedirectResponse("/auth/login?exists=1", status_code=303)

    u = User(email=email, password_hash=hash_password(password), verified=False, is_admin=False)
    db.add(u)
    db.commit()
    db.refresh(u)

    token = create_token({"uid": u.id, "email": u.email}, expires_minutes=60 * 24 * 3)

    # Send verification email in background to avoid blocking
    if isinstance(background_tasks, BackgroundTasks):
        background_tasks.add_task(send_verification_email, u.email, token)
    else:
        # Fallback: run synchronously if for some reason BackgroundTasks not provided
        try:
            send_verification_email(u.email, token)
        except Exception as e:
            logger.warning("Failed to send verification email to %s: %s", u.email, e)

    return RedirectResponse("/auth/login?check_email=1", status_code=303)


@app.get("/auth/verify")
async def verify(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    try:
        data = decode_token(token)
        u = db.query(User).filter(User.id == data["uid"]).first()
        if u:
            u.verified = True
            db.commit()
            return RedirectResponse("/auth/login?verified=1", status_code=303)
    except Exception as e:
        logger.warning("Verification failed: %s", e)
        return templates.TemplateResponse(
            "verify.html",
            {"request": request, "success": False, "user": user, "UI_BRAND_NAME": UI_BRAND_NAME},
        )
    return RedirectResponse("/auth/login", status_code=303)


@app.get("/auth/login")
async def login_get(request: Request, user: Optional[User] = Depends(get_current_user)):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "user": user, "UI_BRAND_NAME": UI_BRAND_NAME},
    )


@app.post("/auth/magic/request")
async def magic_request(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None,  # <-- NO Depends(); FastAPI injects this automatically
):
    # Privacy: do not reveal account existence status
    smtp_status = "skip"
    u = db.query(User).filter(User.email == email).first()
    if u and getattr(u, "verified", False):
        token = create_token({"uid": u.id, "email": u.email, "type": "magic"}, expires_minutes=15)
        # Queue in background; no request-time blocking
        if isinstance(background_tasks, BackgroundTasks):
            background_tasks.add_task(_send_magic_login_email, u.email, token)
            smtp_status = "queued" if MAGIC_EMAIL_ENABLED else "disabled"
        else:
            # Fallback: try sync send
            _send_magic_login_email(u.email, token)
            smtp_status = "attempted"

    # Return success UI but include a developer hint on SMTP status
    return RedirectResponse(f"/auth/login?magic_sent=1&smtp={smtp_status}", status_code=303)


@app.get("/auth/magic")
async def magic_login(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
):
    try:
        data = decode_token(token)
        uid = data.get("uid")
        if not uid or data.get("type") != "magic":
            return RedirectResponse("/auth/login?error=1", status_code=303)

        u = db.query(User).filter(User.id == uid).first()
        if not u or not getattr(u, "verified", False):
            return RedirectResponse("/auth/login?error=1", status_code=303)

        session_token = create_token({"uid": u.id, "email": u.email}, expires_minutes=60 * 24 * 30)
        resp = RedirectResponse("/auth/dashboard", status_code=303)
        _set_session_cookie(resp, session_token)
        return resp
    except Exception as e:
        logger.warning("Magic login failed: %s", e)
        return RedirectResponse("/auth/login?error=1", status_code=303)


@app.post("/auth/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    u = db.query(User).filter(User.email == email).first()
    if not u or not verify_password(password, u.password_hash) or not u.verified:
        return RedirectResponse("/auth/login?error=1", status_code=303)

    token = create_token({"uid": u.id, "email": u.email}, expires_minutes=60 * 24 * 30)
    resp = RedirectResponse("/auth/dashboard", status_code=303)
    _set_session_cookie(resp, token)
    return resp


@app.get("/auth/logout")
async def logout(request: Request):
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("session_token")
    return resp


# ------------------------------------------------------------------------------
# Dashboard & audits (registered flows)
# ------------------------------------------------------------------------------
@app.get("/auth/dashboard")
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    websites = db.query(Website).filter(Website.user_id == user.id).all()

    last_audits = (
        db.query(Audit)
        .filter(Audit.user_id == user.id)
        .order_by(Audit.created_at.desc())
        .limit(10)
        .all()
    )

    avg = round(sum(a.health_score for a in last_audits) / len(last_audits), 1) if last_audits else 0
    trend_labels = [a.created_at.strftime("%d %b") for a in reversed(last_audits)]
    trend_values = [a.health_score for a in reversed(last_audits)]

    summary = {
        "grade": (last_audits[0].grade if last_audits else "A"),
        "health_score": (last_audits[0].health_score if last_audits else 88),
    }

    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    schedule = {
        "daily_time": getattr(sub, "daily_time", "09:00"),
        "timezone": getattr(sub, "timezone", "UTC"),
        "enabled": getattr(sub, "email_schedule_enabled", False),
    }

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "UI_BRAND_NAME": UI_BRAND_NAME,
            "user": user,
            "websites": websites,
            "trend": {"labels": trend_labels, "values": trend_values, "average": avg},
            "summary": summary,
            "schedule": schedule,
        },
    )


@app.get("/auth/audit/new")
async def new_audit_get(request: Request, user: Optional[User] = Depends(get_current_user)):
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    return templates.TemplateResponse(
        "new_audit.html",
        {"request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": user},
    )


@app.post("/auth/audit/new")
async def new_audit_post(
    request: Request,
    url: str = Form(...),
    enable_schedule: str = Form(None),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    if not sub:
        sub = Subscription(user_id=user.id, plan="free", active=True, audits_used=0)
        db.add(sub)
        db.commit()
        db.refresh(sub)

    if enable_schedule and hasattr(sub, "email_schedule_enabled"):
        sub.email_schedule_enabled = True
        db.commit()

    w = Website(user_id=user.id, url=url)
    db.add(w)
    db.commit()
    db.refresh(w)

    return RedirectResponse(f"/auth/audit/run/{w.id}", status_code=303)


@app.get("/auth/audit/run/{website_id}")
async def run_audit(
    website_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    w = db.query(Website).filter(Website.id == website_id, Website.user_id == user.id).first()
    if not w:
        return RedirectResponse("/auth/dashboard", status_code=303)

    try:
        normalized, res = _robust_audit(w.url)
    except Exception as e:
        logger.warning("Audit engine failed: %s", e)
        return RedirectResponse("/auth/dashboard", status_code=303)

    category_scores_dict: Dict[str, int] = {k: int(v) for k, v in (res["category_scores"] or {}).items()}
    overall = compute_overall(category_scores_dict)
    grade = grade_from_score(overall)
    top_issues = res.get("top_issues", [])
    exec_summary = summarize_200_words(normalized, category_scores_dict, top_issues)
    category_scores_list = [{"name": k, "score": int(v)} for k, v in category_scores_dict.items()]

    audit = Audit(
        user_id=user.id,
        website_id=w.id,
        health_score=int(overall),
        grade=grade,
        exec_summary=exec_summary,
        category_scores_json=json.dumps(category_scores_list),
        metrics_json=json.dumps(res.get("metrics", {})),
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)

    w.last_audit_at = audit.created_at
    w.last_grade = grade
    db.commit()

    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    if sub:
        sub.audits_used = (sub.audits_used or 0) + 1
        db.commit()

    return RedirectResponse(f"/auth/audit/{w.id}", status_code=303)


@app.get("/auth/audit/{website_id}")
async def audit_detail(
    website_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    w = db.query(Website).filter(Website.id == website_id, Website.user_id == user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    if not w or not a:
        return RedirectResponse("/auth/dashboard", status_code=303)

    category_scores = json.loads(a.category_scores_json) if a.category_scores_json else []
    metrics_raw = json.loads(a.metrics_json) if a.metrics_json else {}
    metrics = _present_metrics(metrics_raw)

    history = (
        db.query(Audit)
        .filter(Audit.website_id == website_id)
        .order_by(Audit.created_at.desc())
        .limit(12)
        .all()
    )
    trend_labels = [h.created_at.strftime("%d %b") for h in reversed(history)]
    trend_values = [h.health_score for h in reversed(history)]

    radar_labels = [item["name"] for item in category_scores]
    radar_values = [int(item["score"]) for item in category_scores]

    return templates.TemplateResponse(
        "audit_detail.html",
        {
            "request": request,
            "UI_BRAND_NAME": UI_BRAND_NAME,
            "user": user,
            "website": w,
            "audit": {
                "created_at": a.created_at,
                "grade": a.grade,
                "health_score": a.health_score,
                "exec_summary": a.exec_summary,
                "category_scores": category_scores,
                "metrics": metrics,
                "competitor_comparison": list(_get_competitor_comparison({s["name"]: int(s["score"]) for s in category_scores})),
            },
            "chart": {
                "radar_labels": radar_labels,
                "radar_values": radar_values,
                "health": a.health_score,
                "trend_labels": trend_labels,
                "trend_values": trend_values,
            },
        },
    )


@app.get("/auth/report/pdf/{website_id}")
async def report_pdf(
    website_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    w = db.query(Website).filter(Website.id == website_id, Website.user_id == user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    if not w or not a:
        return RedirectResponse("/auth/dashboard", status_code=303)

    category_scores = json.loads(a.category_scores_json) if a.category_scores_json else []
    path = f"/tmp/certified_audit_{website_id}.pdf"

    render_pdf(path, UI_BRAND_NAME, w.url, a.grade, a.health_score, category_scores, a.exec_summary)
    return FileResponse(path, filename=f"{UI_BRAND_NAME}_Certified_Audit_{website_id}.pdf")


# ------------------------------------------------------------------------------
# Scheduling UI & updates
# ------------------------------------------------------------------------------
@app.get("/auth/schedule")
async def schedule_get(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    schedule = {
        "daily_time": getattr(sub, "daily_time", "09:00"),
        "timezone": getattr(sub, "timezone", "UTC"),
        "enabled": getattr(sub, "email_schedule_enabled", False),
    }

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "UI_BRAND_NAME": UI_BRAND_NAME,
            "user": user,
            "websites": db.query(Website).filter(Website.user_id == user.id).all(),
            "trend": {"labels": [], "values": [], "average": 0},
            "summary": {"grade": "A", "health_score": 88},
            "schedule": schedule,
        },
    )


@app.post("/auth/schedule")
async def schedule_post(
    request: Request,
    daily_time: str = Form(...),
    timezone: str = Form(...),
    enabled: str = Form(None),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    if not sub:
        sub = Subscription(user_id=user.id, plan="free", active=True, audits_used=0)
        db.add(sub)
        db.commit()
        db.refresh(sub)

    if hasattr(sub, "daily_time"):
        sub.daily_time = daily_time
    if hasattr(sub, "timezone"):
        sub.timezone = timezone
    if hasattr(sub, "email_schedule_enabled"):
        sub.email_schedule_enabled = bool(enabled)

    db.commit()
    return RedirectResponse("/auth/dashboard", status_code=303)


# ------------------------------------------------------------------------------
# Admin
# ------------------------------------------------------------------------------
@app.get("/auth/admin/login")
async def admin_login_get(request: Request, user: Optional[User] = Depends(get_current_user)):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": user},
    )


@app.post("/auth/admin/login")
async def admin_login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    u = db.query(User).filter(User.email == email).first()
    if not u or not verify_password(password, u.password_hash) or not u.is_admin:
        return RedirectResponse("/auth/admin/login?error=1", status_code=303)

    token = create_token({"uid": u.id, "email": u.email, "admin": True}, expires_minutes=60 * 24 * 30)
    resp = RedirectResponse("/auth/admin", status_code=303)
    _set_session_cookie(resp, token)
    return resp


@app.get("/auth/admin")
async def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user or not user.is_admin:
        return RedirectResponse("/auth/admin/login", status_code=303)

    users = db.query(User).order_by(User.created_at.desc()).limit(100).all()
    audits = db.query(Audit).order_by(Audit.created_at.desc()).limit(100).all()
    websites = db.query(Website).order_by(Website.created_at.desc()).limit(100).all()

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "UI_BRAND_NAME": UI_BRAND_NAME,
            "user": user,
            "websites": websites,
            "admin_users": users,
            "admin_audits": audits,
        },
    )


# ------------------------------------------------------------------------------
# Daily Email Scheduler
# ------------------------------------------------------------------------------
async def _daily_scheduler_loop() -> None:
    """Runs once per minute, sending daily emails at the configured local time."""
    while True:
        try:
            if not MAGIC_EMAIL_ENABLED:
                # Avoid hitting blocked networks entirely
                await asyncio.sleep(60)
                continue

            db = SessionLocal()
            subs = db.query(Subscription).filter(Subscription.active == True).all()
            now_utc = datetime.utcnow()
            for sub in subs:
                if not getattr(sub, "email_schedule_enabled", False):
                    continue
                tz_name = getattr(sub, "timezone", "UTC") or "UTC"
                daily_time = getattr(sub, "daily_time", "09:00") or "09:00"
                try:
                    tz = ZoneInfo(tz_name)
                except Exception:
                    tz = ZoneInfo("UTC")
                local_now = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
                hhmm_now = local_now.strftime("%H:%M")
                if hhmm_now != daily_time:
                    continue
                user = db.query(User).filter(User.id == sub.user_id).first()
                if not user or not getattr(user, "verified", False):
                    continue
                websites = db.query(Website).filter(Website.user_id == user.id).all()
                lines = [
                    f"<h3>Daily Website Audit Summary – {UI_BRAND_NAME}</h3>",
                    f"<p>Hello, {user.email}!</p>",
                    "<p>Here is your daily summary. Download certified PDFs via links below.</p>",
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
                    pdf_link = f"{BASE_URL}/auth/report/pdf/{w.id}"
                    lines.append(
                        f"<p><b>{w.url}</b>: Grade <b>{last.grade}</b>, Health <b>{last.health_score}</b>/100 "
                        f"(<a href=\"{pdf_link}\" target=\"_blank\" rel=\"noopener noreferrer\">Download Certified Report</a>)</p>"
                    )
                thirty_days_ago = datetime.utcnow() - timedelta(days=30)
                audits_30 = db.query(Audit).filter(
                    Audit.user_id == user.id, Audit.created_at >= thirty_days_ago
                ).all()
                if audits_30:
                    avg_score = round(sum(a.health_score for a in audits_30) / len(audits_30), 1)
                    lines.append(f"<hr><p><b>30-day accumulated score:</b> {avg_score}/100</p>")
                else:
                    lines.append("<hr><p><b>30-day accumulated score:</b> Not enough data yet.</p>")
                html = "\n".join(lines)
                _send_report_email(user.email, f"{UI_BRAND_NAME} – Daily Website Audit Summary", html)
            db.close()
        except Exception as e:
            logger.warning("Scheduler loop error: %s", e)
        await asyncio.sleep(60)


@app.on_event("startup")
async def _start_scheduler():
    if not MAGIC_EMAIL_ENABLED:
        logger.warning("Startup: MAGIC_EMAIL_ENABLED=false (emails will NOT be sent).")
    else:
        if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
            logger.warning("Startup: SMTP credentials missing; emails will NOT be sent.")
        else:
            logger.info(f"Startup: SMTP configured for {SMTP_USER} via {SMTP_HOST}:{SMTP_PORT}, timeout={SMTP_TIMEOUT_SEC}s")
    asyncio.create_task(_daily_scheduler_loop())


# ------------------------------------------------------------------------------
# Run locally binding to environment PORT (Railway sets PORT automatically)
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, workers=1)
