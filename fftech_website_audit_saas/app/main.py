
"""
FFTech Website Audit SaaS — Web App Entrypoint (relative-import safe)

- Uses only RELATIVE imports so it works with:
  uvicorn app.main:app
  or
  uvicorn fftech_website_audit_saas.app.main:app
"""

import os
import json
import time
import uuid
import base64
import hmac
import hashlib
from typing import Any, Dict, List, Optional

from fastapi import (
    FastAPI, Request, Depends, Form,
    HTTPException, status, BackgroundTasks
)
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import jwt  # pyjwt

# ---------------------------
# Local package imports (RELATIVE)
# ---------------------------
from .db import SessionLocal, engine
from .models import Base, User, Website, Audit, Subscription

# Audit modules (under app/audit) — relative imports
from .audit.engine import run_basic_checks, run_competitor_analysis_one_page  # noqa: F401 (kept for future)
from .audit.grader import compute_overall, grade_from_score, summarize_200_words
from .audit.report import render_pdf

# Email helpers (optional)
from .email_utils import (
    send_report_email,
    send_verification_email,
    build_verification_link,
)

# ===========================
# Configuration via ENV
# ===========================
UI_BRAND_NAME = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# Sessions / JWT
SESSION_SECRET = os.getenv("SESSION_SECRET", "replace-session-secret")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-please")
JWT_ALGO = os.getenv("JWT_ALGO", "HS256")
JWT_COOKIE_NAME = os.getenv("JWT_COOKIE_NAME", "access_token")

# Password hashing
AUTH_SALT = os.getenv("AUTH_SALT", "fftech_salt").encode()
AUTH_ITERATIONS = int(os.getenv("AUTH_ITERATIONS", "200000"))

# Reports
REPORT_DIR = os.getenv("REPORT_DIR", os.path.join(os.path.dirname(__file__), "reports"))
os.makedirs(REPORT_DIR, exist_ok=True)

# Email toggle
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"

# Competitor baseline for open audit
INDUSTRY_BASELINE = int(os.getenv("INDUSTRY_BASELINE", "82"))

# ===========================
# App + Middleware
# ===========================
app = FastAPI(title="FFTech Website Audit SaaS", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, https_only=False)

# Create database tables
Base.metadata.create_all(bind=engine)

# Resolve templates directory relative to this file (works regardless of CWD)
TEMPLATES_DIR = os.getenv(
    "TEMPLATES_DIR",
    os.path.join(os.path.dirname(__file__), "templates")
)
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ===========================
# DB dependency
# ===========================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ===========================
# Auth utilities (PBKDF2 + JWT)
# ===========================
def hash_password(plain: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode(), AUTH_SALT, AUTH_ITERATIONS)
    return f"pbkdf2_sha256${AUTH_ITERATIONS}${dk.hex()}"

def verify_password(plain: str, stored: str) -> bool:
    try:
        method, iter_str, hex_hash = stored.split("$")
        if method != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        test = hashlib.pbkdf2_hmac("sha256", plain.encode(), AUTH_SALT, iterations)
        return hmac.compare_digest(test.hex(), hex_hash)
    except Exception:
        return False

def create_token(payload: dict, expires_minutes: int = 60) -> str:
    now = int(time.time())
    exp = now + expires_minutes * 60
    to_encode = dict(payload)
    to_encode.update({"iat": now, "exp": exp})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGO)

def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])

# ===========================
# Helpers
# ===========================
def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def get_user_from_session(request: Request, db: Session) -> Optional[User]:
    token = request.session.get(JWT_COOKIE_NAME)
    if not token:
        return None
    try:
        payload = decode_token(token)
        uid = int(payload.get("sub", "0"))
        if not uid:
            return None
        return db.get(User, uid)
    except Exception:
        return None

def require_auth_user(request: Request, db: Session) -> User:
    user = get_user_from_session(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user

def require_admin_user(request: Request, db: Session) -> User:
    user = require_auth_user(request, db)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only.")
    return user

def base_ctx(request: Request, user: Optional[User] = None) -> Dict[str, Any]:
    return {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "year": time.strftime("%Y"),
        "user": user,
    }

def _baseline_rows(category_scores: Dict[str, int], baseline: int) -> List[Dict[str, Any]]:
    rows = []
    for cat, score in category_scores.items():
        gap = int(score) - baseline
        rows.append({
            "category": cat,
            "target": int(score),
            "competitor": int(baseline),
            "status": "Lead" if gap >= 0 else "Lag",
        })
    return rows

def _scores_list(category_scores: Dict[str, int]) -> List[Dict[str, Any]]:
    order = ["Performance", "Accessibility", "SEO", "Security", "BestPractices"]
    return [{"name": k, "score": int(category_scores.get(k, 0))} for k in order]

# ===========================
# Public Views
# ===========================
@app.get("/", response_class=HTMLResponse)
def landing(request: Request, db: Session = Depends(get_db)):
    user = get_user_from_session(request, db)
    return templates.TemplateResponse("index.html", base_ctx(request, user))

@app.post("/audit/open", response_class=HTMLResponse)
def audit_open(request: Request, url: str = Form(...), db: Session = Depends(get_db)):
    user = get_user_from_session(request, db)
    res = run_basic_checks(url)
    cats: Dict[str, int] = res.get("category_scores", {})
    issues: List[str] = res.get("top_issues", [])
    metrics: Dict[str, Any] = res.get("metrics", {})
    total = compute_overall(cats)
    grade = grade_from_score(total)
    summary = summarize_200_words(url, cats, issues)
    competitor_rows = _baseline_rows(cats, INDUSTRY_BASELINE)
    ctx = {
        **base_ctx(request, user),
        "website": {"url": url},
        "audit": {
            "health_score": total,
            "grade": grade,
            "exec_summary": summary,
            "metrics": metrics,
            "competitor_comparison": competitor_rows,
        },
    }
    return templates.TemplateResponse("audit_detail_open.html", ctx)

@app.get("/report/pdf/open")
def report_pdf_open(request: Request, url: str, db: Session = Depends(get_db)):
    user = get_user_from_session(request, db)
    res = run_basic_checks(url)
    cats: Dict[str, int] = res.get("category_scores", {})
    issues: List[str] = res.get("top_issues", [])
    total = compute_overall(cats)
    grade = grade_from_score(total)
    summary = summarize_200_words(url, cats, issues)
    category_scores_list = _scores_list(cats)
    filename = f"{uuid.uuid4().hex}_open_audit.pdf"
    out_path = os.path.join(REPORT_DIR, filename)
    render_pdf(
        path=out_path,
        brand_name=UI_BRAND_NAME,
        url=url,
        grade=grade,
        health_score=total,
        category_scores=category_scores_list,
        exec_summary=summary,
    )
    return FileResponse(out_path, media_type="application/pdf", filename=f"{UI_BRAND_NAME}-audit-open.pdf")

# ===========================
# Auth (Register / Verify / Login / Logout)
# ===========================
@app.get("/auth/register", response_class=HTMLResponse)
def register_form(request: Request, db: Session = Depends(get_db)):
    user = get_user_from_session(request, db)
    if user:
        return RedirectResponse("/auth/dashboard", status_code=302)
    return templates.TemplateResponse("register.html", base_ctx(request, None))

@app.post("/auth/register")
def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    if password != confirm_password:
        return RedirectResponse(url="/auth/register?mismatch=1", status_code=302)

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return RedirectResponse(url="/auth/login", status_code=302)

    stored = hash_password(password)
    user = User(email=email, password_hash=stored, verified=False, is_admin=False)
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token({"sub": str(user.id)}, expires_minutes=60 * 24)
    if EMAIL_ENABLED:
        try:
            link = build_verification_link(BASE_URL, token)
            send_verification_email(to_email=user.email, brand=UI_BRAND_NAME, verify_link=link)
        except Exception:
            pass

    return RedirectResponse(url="/auth/login", status_code=302)

@app.get("/auth/verify", response_class=HTMLResponse)
def verify_email(request: Request, token: Optional[str] = None, db: Session = Depends(get_db)):
    ok = False
    try:
        if token:
            payload = decode_token(token)
            uid = int(payload.get("sub", "0"))
            user = db.get(User, uid)
            if user:
                user.verified = True
                db.commit()
                ok = True
    except Exception:
        ok = False
    ctx = {**base_ctx(request, None), "success": ok}
    return templates.TemplateResponse("verify.html", ctx)

@app.get("/auth/login", response_class=HTMLResponse)
def login_form(request: Request, db: Session = Depends(get_db)):
    user = get_user_from_session(request, db)
    if user:
        return RedirectResponse("/auth/dashboard", status_code=302)
    # Minimal inline login (since login.html exists in your repo, you may prefer to render it)
    return templates.TemplateResponse("login.html", base_ctx(request, None))

@app.post("/auth/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return RedirectResponse(url="/auth/login", status_code=302)

    token = create_token({"sub": str(user.id)}, expires_minutes=60 * 24)
    request.session[JWT_COOKIE_NAME] = token
    return RedirectResponse(url="/auth/dashboard", status_code=302)

@app.get("/auth/logout")
def logout(request: Request):
    request.session.pop(JWT_COOKIE_NAME, None)
    return RedirectResponse(url="/", status_code=302)

# ===========================
# Authenticated Views
# ===========================
@app.get("/auth/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_auth_user(request, db)
    websites = db.query(Website).filter(Website.user_id == user.id).all()
    audits = db.query(Audit).filter(Audit.user_id == user.id).all()
    avg = int(sum(a.health_score or 0 for a in audits) / max(1, len(audits))) if audits else 0
    ctx = {**base_ctx(request, user), "websites": websites, "trend": {"average": avg}}
    return templates.TemplateResponse("dashboard.html", ctx)

@app.get("/auth/audit/new", response_class=HTMLResponse)
def new_audit_form(request: Request, db: Session = Depends(get_db)):
    user = require_auth_user(request, db)
    return templates.TemplateResponse("new_audit.html", base_ctx(request, user))

@app.post("/auth/audit/new")
def new_audit_submit(
    request: Request,
    url: str = Form(...),
    enable_schedule: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    user = require_auth_user(request, db)

    website = db.query(Website).filter(Website.user_id == user.id, Website.url == url).first()
    if not website:
        website = Website(user_id=user.id, url=url)
        db.add(website)
        db.commit()
        db.refresh(website)

    res = run_basic_checks(url)
    cats: Dict[str, int] = res.get("category_scores", {})
    issues: List[str] = res.get("top_issues", [])
    metrics: Dict[str, Any] = res.get("metrics", {})

    total = compute_overall(cats)
    grade = grade_from_score(total)
    summary = summarize_200_words(url, cats, issues)

    audit = Audit(
        user_id=user.id,
        website_id=website.id,
        health_score=total,
        grade=grade,
        exec_summary=summary,
        category_scores_json=json.dumps(cats, ensure_ascii=False),
        metrics_json=json.dumps(metrics, ensure_ascii=False),
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)

    website.last_audit_at = audit.created_at
    website.last_grade = grade
    db.commit()

    if enable_schedule:
        sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
        if not sub:
            sub = Subscription(user_id=user.id, plan="free", email_schedule_enabled=True)
            db.add(sub)
        else:
            sub.email_schedule_enabled = True
        db.commit()

    if EMAIL_ENABLED:
        try:
            cats_list = _scores_list(cats)
            filename = f"{uuid.uuid4().hex}_audit_{audit.id}.pdf"
            out_path = os.path.join(REPORT_DIR, filename)
            render_pdf(
                path=out_path,
                brand_name=UI_BRAND_NAME,
                url=website.url,
                grade=audit.grade,
                health_score=audit.health_score,
                category_scores=cats_list,
                exec_summary=audit.exec_summary,
            )
            send_report_email(
                to_email=user.email,
                brand=UI_BRAND_NAME,
                pdf_path=out_path,
                website_url=website.url,
                score=audit.health_score,
                grade=audit.grade,
            )
        except Exception:
            pass

    return RedirectResponse(url=f"/auth/audit/{website.id}", status_code=302)

@app.get("/auth/audit/{website_id}", response_class=HTMLResponse)
def audit_detail(website_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_auth_user(request, db)
    website = db.get(Website, website_id)
    if not website or website.user_id != user.id:
        raise HTTPException(status_code=404, detail="Website not found")

    audit = (
        db.query(Audit)
        .filter(Audit.user_id == user.id, Audit.website_id == website.id)
        .order_by(Audit.created_at.desc())
        .first()
    )
    if not audit:
        return RedirectResponse(url="/auth/audit/new", status_code=302)

    cats: Dict[str, int] = json.loads(audit.category_scores_json or "{}")

    radar_labels = ["Performance", "Accessibility", "SEO", "Security", "BestPractices"]
    radar_values = [int(cats.get(k, 0)) for k in radar_labels]

    last_audits = (
        db.query(Audit)
        .filter(Audit.user_id == user.id, Audit.website_id == website.id)
        .order_by(Audit.created_at.asc())
        .all()
    )
    trend_labels = [(a.created_at.strftime("%d %b") if a.created_at else "-") for a in last_audits][-8:]
    trend_values = [int(a.health_score or 0) for a in last_audits][-8:]

    ctx = {
        **base_ctx(request, user),
        "website": website,
        "audit": audit,
        "chart": {
            "health": int(audit.health_score or 0),
            "healthint": int(audit.health_score or 0),
            "radar_labels": radar_labels,
            "radar_values": radar_values,
            "trend_labels": trend_labels,
            "trend_values": trend_values,
        },
    }
    return templates.TemplateResponse("audit_detail.html", ctx)

@app.get("/auth/report/pdf/{website_id}")
def download_pdf_for_website(website_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_auth_user(request, db)
    website = db.get(Website, website_id)
    if not website or website.user_id != user.id:
        raise HTTPException(status_code=404, detail="Website not found")

    audit = (
        db.query(Audit)
        .filter(Audit.user_id == user.id, Audit.website_id == website.id)
        .order_by(Audit.created_at.desc())
        .first()
    )
    if not audit:
        raise HTTPException(status_code=404, detail="No audit to export")

    cats: Dict[str, int] = json.loads(audit.category_scores_json or "{}")
    cats_list = _scores_list(cats)

    filename = f"{uuid.uuid4().hex}_audit_{audit.id}.pdf"
    out_path = os.path.join(REPORT_DIR, filename)

    render_pdf(
        path=out_path,
        brand_name=UI_BRAND_NAME,
        url=website.url,
        grade=audit.grade,
        health_score=audit.health_score,
        category_scores=cats_list,
        exec_summary=audit.exec_summary,
    )

    return FileResponse(out_path, media_type="application/pdf", filename=f"{UI_BRAND_NAME}-audit-{audit.id}.pdf")

# ===========================
# Admin Panel
# ===========================
@app.get("/admin", response_class=HTMLResponse)
def admin_panel(request: Request, db: Session = Depends(get_db)):
    admin = require_admin_user(request, db)
    users = db.query(User).order_by(User.created_at.desc()).limit(100).all()
    websites = db.query(Website).order_by(Website.created_at.desc()).limit(100).all()
    audits = db.query(Audit).order_by(Audit.created_at.desc()).limit(100).all()
    ctx = {**base_ctx(request, admin), "admin_users": users, "websites": websites, "admin_audits": audits}
    return templates.TemplateResponse("admin.html", ctx)

# ===========================
# Health
# ===========================
@app.get("/health")
def health():
    return {"status": "ok", "time": now_iso(), "brand": UI_BRAND_NAME}
``
