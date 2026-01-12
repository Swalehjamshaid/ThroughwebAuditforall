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
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import Base, engine, SessionLocal
from .models import User, Website, Audit, Subscription
from .auth import hash_password, verify_password, create_token, decode_token
from .email_utils import send_verification_email
from .audit.engine import run_basic_checks
from .audit.grader import compute_overall, grade_from_score, summarize_200_words
from .audit.report import render_pdf

# -------------------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------------------
UI_BRAND_NAME: str = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")

SMTP_HOST: Optional[str] = os.getenv("SMTP_HOST")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: Optional[str] = os.getenv("SMTP_USER")
SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD")

ADMIN_EMAIL: Optional[str] = os.getenv("ADMIN_EMAIL")
COMPETITOR_BASELINE_JSON: Optional[str] = os.getenv(
    "COMPETITOR_BASELINE_JSON",
    '{"Performance": 82, "Accessibility": 88, "SEO": 85, "Security": 90, "BestPractices": 84}',
)

# -------------------------------------------------------------------------------
# Logging
# -------------------------------------------------------------------------------
logger = logging.getLogger("fftech.app")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

# -------------------------------------------------------------------------------
# FastAPI app, static & templates
# -------------------------------------------------------------------------------
app = FastAPI(title=f"{UI_BRAND_NAME} — Website Audit SaaS")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")
templates.env.globals.update({
    "datetime": datetime,
    "UI_BRAND_NAME": UI_BRAND_NAME,
    "year": datetime.utcnow().year,
    "now": datetime.utcnow(),
})

# -------------------------------------------------------------------------------
# DB schema initialization & patches
# -------------------------------------------------------------------------------
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

# -------------------------------------------------------------------------------
# DB dependency & per-request user dependency
# -------------------------------------------------------------------------------
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

# -------------------------------------------------------------------------------
# Security headers middleware
# -------------------------------------------------------------------------------
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

# -------------------------------------------------------------------------------
# Health & readiness
# -------------------------------------------------------------------------------
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

# -------------------------------------------------------------------------------
# Metric labels & presenters
# -------------------------------------------------------------------------------
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

# -------------------------------------------------------------------------------
# User authentication & session management routes
# -------------------------------------------------------------------------------
@app.post("/login")
async def login(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
    response: Response = None,
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password):
        return JSONResponse({"error": "Invalid credentials"}, status_code=401)
    if not user.verified:
        return JSONResponse({"error": "Email not verified"}, status_code=403)

    token = create_token({"uid": user.id})
    response.set_cookie("session_token", token, httponly=True, max_age=86400)
    return JSONResponse({"status": "success"})


@app.post("/register")
async def register(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    hashed = hash_password(password)
    user = User(email=email, password=hashed, verified=False)
    db.add(user)
    db.commit()
    db.refresh(user)
    send_verification_email(user.email)
    return JSONResponse({"status": "verification_sent"})


@app.get("/logout")
async def logout(response: Response):
    response.delete_cookie("session_token")
    return RedirectResponse("/login")

# -------------------------------------------------------------------------------
# Dashboard & website audit routes
# -------------------------------------------------------------------------------
@app.get("/")
async def dashboard(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return RedirectResponse("/login")
    websites = db.query(Website).filter(Website.user_id == user.id).all()
    return templates.TemplateResponse("dashboard.html", {"request": request, "websites": websites, "user": user})


@app.post("/audit")
async def audit_website(
    url: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user:
        return JSONResponse({"error": "Authentication required"}, status_code=401)
    metrics = run_basic_checks(url)
    overall_score = compute_overall(metrics)
    grade = grade_from_score(overall_score)
    summary = summarize_200_words(metrics)
    audit = Audit(user_id=user.id, url=url, metrics=json.dumps(metrics), overall=overall_score, grade=grade)
    db.add(audit)
    db.commit()
    return JSONResponse({"metrics": _present_metrics(metrics), "overall": overall_score, "grade": grade, "summary": summary})


@app.get("/audit/{audit_id}/pdf")
async def audit_pdf(audit_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    audit = db.query(Audit).filter(Audit.id == audit_id, Audit.user_id == user.id).first()
    if not audit:
        return JSONResponse({"error": "Audit not found"}, status_code=404)
    file_path = render_pdf(audit)
    return FileResponse(file_path, media_type="application/pdf", filename=f"audit_{audit.id}.pdf")

# -------------------------------------------------------------------------------
# Scheduler for email reports
# -------------------------------------------------------------------------------
async def schedule_email_reports():
    while True:
        try:
            with SessionLocal() as db:
                subscriptions: Iterable[Subscription] = db.query(Subscription).filter(
                    Subscription.email_schedule_enabled == True
                ).all()
                for sub in subscriptions:
                    now = datetime.now(ZoneInfo(sub.timezone))
                    sched_time = datetime.strptime(sub.daily_time, "%H:%M").replace(
                        year=now.year, month=now.month, day=now.day, tzinfo=ZoneInfo(sub.timezone)
                    )
                    if now >= sched_time and not sub.last_sent or sub.last_sent.date() < now.date():
                        # Send email
                        user = db.query(User).filter(User.id == sub.user_id).first()
                        if user:
                            send_verification_email(user.email)
                        sub.last_sent = now
                        db.commit()
        except Exception as e:
            logger.error("Scheduler error: %s", e)
        await asyncio.sleep(60)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(schedule_email_reports())

