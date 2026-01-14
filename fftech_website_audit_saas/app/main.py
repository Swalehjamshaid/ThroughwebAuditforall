
"""
FFTech Website Audit SaaS — Web App Entrypoint

Stack:
- FastAPI + Jinja2 templates
- SQLAlchemy models (users, websites, audits, subscription)
- Session cookie (HTTPOnly) storing a JWT for auth
- Audit engine (heuristics) + grading + PDF generation
- Optional email (Resend) via email_utils

Templates considered:
index.html, audit_detail_open.html, audit_detail.html, dashboard.html,
new_audit.html, register.html, verify.html, admin.html, base.html
"""

import os
import json
import time
import uuid
import base64
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

# ---------------------------
# Local package imports
# ---------------------------
from fftech_website_audit_saas.app.db import SessionLocal, engine
from fftech_website_audit_saas.app.models import Base, User, Website, Audit, Subscription

# Audit modules (under app/audit)
# Engine (heuristics + competitor analysis)  [1](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/engine.py)
from fftech_website_audit_saas.app.audit.engine import (
    run_basic_checks,
    run_competitor_analysis_one_page,   # kept for optional extension
)

# Grader (overall/grade/summary)  [2](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/grader.py)
from fftech_website_audit_saas.app.audit.grader import (
    compute_overall,
    grade_from_score,
    summarize_200_words,
)

# Report (PDF)  [3](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/report.py)
from fftech_website_audit_saas.app.audit.report import render_pdf

# Optional emails (Resend)
from fftech_website_audit_saas.app.email_utils import (
    send_report_email,
    send_verification_email,
    build_verification_link,
)

# JWT + password hashing
import jwt
import hmac
import hashlib


# ===========================
# Configuration via ENV
# ===========================
UI_BRAND_NAME = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Sessions / JWT
SESSION_SECRET = os.getenv("SESSION_SECRET", "replace-session-secret")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-please")
JWT_ALGO = os.getenv("JWT_ALGO", "HS256")
JWT_COOKIE_NAME = os.getenv("JWT_COOKIE_NAME", "access_token")

# Password hashing
AUTH_SALT = os.getenv("AUTH_SALT", "fftech_salt").encode()
AUTH_ITERATIONS = int(os.getenv("AUTH_ITERATIONS", "200000"))

# Reports
REPORT_DIR = os.getenv("REPORT_DIR", "./reports")
os.makedirs(REPORT_DIR, exist_ok=True)

# Email toggle
EMAIL_ENABLED = bool(os.getenv("EMAIL_ENABLED", "false").lower() == "true")

# Competitor baseline used on open-audit template table
INDUSTRY_BASELINE = int(os.getenv("INDUSTRY_BASELINE", "82"))


# ===========================
# App + Middleware
# ===========================
app = FastAPI(title="FFTech Website Audit SaaS", version="1.0.0")

# Allow your UI origins (tighten in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cookie-backed session (used to keep JWT in HttpOnly cookie)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, https_only=False)

# Create database tables
Base.metadata.create_all(bind=engine)

# Jinja templates
TEMPLATES_DIR = os.getenv("TEMPLATES_DIR", "templates")
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
    """
    Rows for 'Competitor Benchmark Analysis' table in audit_detail_open.html:
    Category | Your Score | Industry Avg | Status(Lead/Lag)
    """
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
    # index.html (public landing with open audit form)  [1](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/engine.py)
    user = get_user_from_session(request, db)
    return templates.TemplateResponse("index.html", base_ctx(request, user))


@app.post("/audit/open", response_class=HTMLResponse)
def audit_open(request: Request, url: str = Form(...), db: Session = Depends(get_db)):
    """
    Public (no-auth) single-page audit used by index.html form.
    Renders audit_detail_open.html with baseline competitor comparison.
    """
    user = get_user_from_session(request, db)

    res = run_basic_checks(url)  # heuristics [1](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/engine.py)
    cats: Dict[str, int] = res.get("category_scores", {})
    issues: List[str] = res.get("top_issues", [])
    metrics: Dict[str, Any] = res.get("metrics", {})

    total = compute_overall(cats)             # [2](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/grader.py)
    grade = grade_from_score(total)           # [2](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/grader.py)
    summary = summarize_200_words(url, cats, issues)  # [2](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/grader.py)

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
    # audit_detail_open.html (public audit result)  [2](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/grader.py)
    return templates.TemplateResponse("audit_detail_open.html", ctx)


@app.get("/report/pdf/open")
def report_pdf_open(request: Request, url: str, db: Session = Depends(get_db)):
    """
    Generates a one-off PDF for a public/open audit (no persistence).
    """
    user = get_user_from_session(request, db)

    res = run_basic_checks(url)               # [1](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/engine.py)
    cats: Dict[str, int] = res.get("category_scores", {})
    issues: List[str] = res.get("top_issues", [])
    metrics: Dict[str, Any] = res.get("metrics", {})

    total = compute_overall(cats)             # [2](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/grader.py)
    grade = grade_from_score(total)           # [2](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/grader.py)
    summary = summarize_200_words(url, cats, issues)  # [2](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/grader.py)
    category_scores_list = _scores_list(cats)

    filename = f"{uuid.uuid4().hex}_open_audit.pdf"
    out_path = os.path.join(REPORT_DIR, filename)

    render_pdf(                            # PDF builder  [3](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/report.py)
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
    # register.html  [3](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/report.py)
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
        # templates expect ?mismatch=1  [3](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/report.py)
        return RedirectResponse(url="/auth/register?mismatch=1", status_code=302)

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return RedirectResponse(url="/auth/login", status_code=302)

    stored = hash_password(password)
    user = User(email=email, password_hash=stored, verified=False, is_admin=False)
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create a verification token + (optional) send email
    token = create_token({"sub": str(user.id)}, expires_minutes=60 * 24)
    if EMAIL_ENABLED:
        try:
            link = build_verification_link(BASE_URL, token)
            send_verification_email(to_email=user.email, brand=UI_BRAND_NAME, verify_link=link)
        except Exception:
            # swallow in demo mode
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
    # verify.html  [1](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/engine.py)
    return templates.TemplateResponse("verify.html", ctx)


@app.get("/auth/login", response_class=HTMLResponse)
def login_form(request: Request, db: Session = Depends(get_db)):
    user = get_user_from_session(request, db)
    if user:
        return RedirectResponse("/auth/dashboard", status_code=302)

    # Inline minimal login page (since no login.html provided)
    html = """
    <!doctype html><html><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Login · {brand}</title>
    https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css
    </head><body class="bg-dark text-light">
    <main class="container py-5">
      <div class="row justify-content-center">
        <div class="col-12 col-md-6 col-lg-5">
          <div class="card bg-secondary bg-opacity-10 border-light">
            <div class="card-body">
              <h4 class="mb-3">Sign In</h4>
              /auth/login
                <div class="col-12">
                  <label class="form-label">Email</label>
                  <input type="email" name="email" class="form-control" required>
                </div>
                <div class="col-12">
                  <label class="form-label">Password</label>
                  <input type="password" name="password" class="form-control" required>
                </div>
                <div class="col-12">
                  <button class="btn btn-primary" type="submit">Login</button>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
    </main>
    </body></html>
    """.format(brand=UI_BRAND_NAME)
    return HTMLResponse(content=html)


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
    request.session[JWT_COOKIE_NAME] = token  # HttpOnly cookie inside session
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

    ctx = {
        **base_ctx(request, user),
        "websites": websites,
        "trend": {"average": avg},
    }
    # dashboard.html  [2](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/grader.py)
    return templates.TemplateResponse("dashboard.html", ctx)


@app.get("/auth/audit/new", response_class=HTMLResponse)
def new_audit_form(request: Request, db: Session = Depends(get_db)):
    user = require_auth_user(request, db)
    # new_audit.html  [1](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/engine.py)
    return templates.TemplateResponse("new_audit.html", base_ctx(request, user))


@app.post("/auth/audit/new")
def new_audit_submit(
    request: Request,
    url: str = Form(...),
    enable_schedule: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    user = require_auth_user(request, db)

    # Ensure website exists for this user
    website = db.query(Website).filter(Website.user_id == user.id, Website.url == url).first()
    if not website:
        website = Website(user_id=user.id, url=url)
        db.add(website)
        db.commit()
        db.refresh(website)

    # Run an immediate audit
    res = run_basic_checks(url)              # [1](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/engine.py)
    cats: Dict[str, int] = res.get("category_scores", {})
    issues: List[str] = res.get("top_issues", [])
    metrics: Dict[str, Any] = res.get("metrics", {})

    total = compute_overall(cats)            # [2](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/grader.py)
    grade = grade_from_score(total)          # [2](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/grader.py)
    summary = summarize_200_words(url, cats, issues)  # [2](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/grader.py)

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

    # Optionally persist schedule flag to Subscription
    if enable_schedule:
        sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
        if not sub:
            sub = Subscription(user_id=user.id, plan="free", email_schedule_enabled=True)
            db.add(sub)
        else:
            sub.email_schedule_enabled = True
        db.commit()

    # Optionally email the PDF to user (demo: send latest one)
    if EMAIL_ENABLED:
        try:
            # Generate a PDF and email it
            cats_list = _scores_list(cats)
            filename = f"{uuid.uuid4().hex}_audit_{audit.id}.pdf"
            out_path = os.path.join(REPORT_DIR, filename)
            render_pdf(                    # [3](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/report.py)
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

    # Latest audit for this website
    audit = (
        db.query(Audit)
        .filter(Audit.user_id == user.id, Audit.website_id == website.id)
        .order_by(Audit.created_at.desc())
        .first()
    )
    if not audit:
        return RedirectResponse(url="/auth/audit/new", status_code=302)

    cats: Dict[str, int] = json.loads(audit.category_scores_json or "{}")
    metrics: Dict[str, Any] = json.loads(audit.metrics_json or "{}")

    # Chart data expected by audit_detail.html  [3](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/report.py)
    radar_labels = ["Performance", "Accessibility", "SEO", "Security", "BestPractices"]
    radar_values = [int(cats.get(k, 0)) for k in radar_labels]

    # Trend chart (latest audits of this website)
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
            "healthint": int(audit.health_score or 0),  # robust to minor template typos
            "radar_labels": radar_labels,
            "radar_values": radar_values,
            "trend_labels": trend_labels,
            "trend_values": trend_values,
        },
    }
    # audit_detail.html  [3](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/report.py)
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

    render_pdf(                        # [3](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/report.py)
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

    ctx = {
        **base_ctx(request, admin),
        "admin_users": users,
        "websites": websites,
        "admin_audits": audits,
    }
    # admin.html  [1](https://haiergroup-my.sharepoint.com/personal/jamshaid_ali_haier_com_pk/Documents/Microsoft%20Copilot%20Chat%20Files/engine.py)
    return templates.TemplateResponse("admin.html", ctx)


# ===========================
# Health
# ===========================
@app.get("/health")
def health():
    return {"status": "ok", "time": now_iso(), "brand": UI_BRAND_NAME}
