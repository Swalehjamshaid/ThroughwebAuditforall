
# fftech_website_audit_saas/app/main.py
import os
import json
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import RedirectResponse, FileResponse
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

# For sending scheduled emails (used inside background loop)
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ---------- Environment ----------
UI_BRAND_NAME   = os.getenv("UI_BRAND_NAME", "FF Tech")
SMTP_HOST       = os.getenv("SMTP_HOST")
SMTP_PORT       = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER       = os.getenv("SMTP_USER")
SMTP_PASSWORD   = os.getenv("SMTP_PASSWORD")
BASE_URL        = os.getenv("BASE_URL", "http://localhost:8000")

# ---------- App & Templates ----------
app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Ensure DB tables exist
Base.metadata.create_all(bind=engine)

# ---- Startup tweaks: add schedule columns safely ----
def _ensure_schedule_columns():
    """Adds daily_time, timezone, email_schedule_enabled columns if missing (Postgres-friendly)."""
    try:
        with engine.connect() as conn:
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
            conn.commit()
    except Exception:
        # Do not block startup if schema change fails
        pass

# ---- Patch old 'users' table safely (idempotent) ----
def _ensure_user_columns():
    """Add missing columns to 'users' if they don't exist (Postgres-friendly)."""
    try:
        with engine.connect() as conn:
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
            conn.commit()
    except Exception:
        pass

_ensure_schedule_columns()
_ensure_user_columns()

# ---------- Dependencies ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------- Session handling (JWT cookie) ----------
current_user = None

@app.middleware("http")
async def session_middleware(request: Request, call_next):
    """
    Hydrates global current_user from a signed cookie if present.
    Keeps compatibility with existing links and templates.
    """
    global current_user
    if current_user is None:
        token = request.cookies.get("session_token")
        if token:
            try:
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

# ---------- Pages ----------

@app.get("/")
async def index(request: Request):
    # Open audit landing uses base_open.html via index.html
    return templates.TemplateResponse("index.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user
    })

# --- Open audit (no registration required) ---
@app.post("/audit/open")
async def audit_open(request: Request):
    form = await request.form()
    url = form.get("url")
    if not url:
        return RedirectResponse("/", status_code=303)

    # Run an audit without saving to DB
    res = run_basic_checks(url)
    category_scores_dict = res["category_scores"]
    overall = compute_overall(category_scores_dict)
    grade = grade_from_score(overall)
    exec_summary = summarize_200_words(url, category_scores_dict, res["top_issues"])
    category_scores_list = [{"name": k, "score": int(v)} for k, v in category_scores_dict.items()]

    data = {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user,
        # pass a lightweight website object
        "website": {"id": None, "url": url},
        "audit": {
            "created_at": datetime.utcnow(),
            "grade": grade,
            "health_score": int(overall),
            "exec_summary": exec_summary,
            "category_scores": category_scores_list,
            "metrics": res["metrics"]
        }
    }
    return templates.TemplateResponse("audit_detail_open.html", data)

@app.get("/report/pdf/open")
async def report_pdf_open(url: str):
    # Generate PDF directly from URL (no DB)
    res = run_basic_checks(url)
    cs_list = [{"name": k, "score": int(v)} for k, v in res["category_scores"].items()]
    overall = compute_overall(res["category_scores"])
    grade = grade_from_score(overall)
    exec_summary = summarize_200_words(url, res["category_scores"], res["top_issues"])
    path = "/tmp/certified_audit_open.pdf"
    render_pdf(path, UI_BRAND_NAME, url, grade, int(overall), cs_list, exec_summary)
    return FileResponse(path, filename=f"{UI_BRAND_NAME}_Certified_Audit_Open.pdf")

# --- Registration & Auth ---
@app.get("/register")
async def register_get(request: Request):
    # Registration page uses base_register.html via register.html
    return templates.TemplateResponse("register.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user
    })

@app.post("/register")
async def register_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    if password != confirm_password:
        return RedirectResponse("/register", status_code=303)
    if db.query(User).filter(User.email == email).first():
        return RedirectResponse("/login", status_code=303)
    u = User(email=email, password_hash=hash_password(password), verified=False, is_admin=False)
    db.add(u); db.commit(); db.refresh(u)
    token = create_token({"uid": u.id, "email": u.email}, expires_minutes=60*24*3)
    try:
        send_verification_email(u.email, token)
    except Exception:
        # Email failures should not block registration
        pass
    # Optional: show a hint on login page
    return RedirectResponse("/login?check_email=1", status_code=303)

@app.get("/verify")
async def verify(request: Request, token: str, db: Session = Depends(get_db)):
    """
    Marks user verified when the emailed link (/verify?token=...) is clicked,
    then redirects to /login with a success flag.
    """
    try:
        data = decode_token(token)
        u = db.query(User).filter(User.id == data["uid"]).first()
        if u:
            u.verified = True
            db.commit()
            # Redirect straight to login so user can sign in
            return RedirectResponse("/login?verified=1", status_code=303)
    except Exception:
        # If token invalid/expired, show verify page with failure
        return templates.TemplateResponse("verify.html", {
            "request": request,
            "success": False,
            "UI_BRAND_NAME": UI_BRAND_NAME,
            "user": current_user
        })

    return RedirectResponse("/login", status_code=303)

@app.get("/login")
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user
    })

@app.post("/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    global current_user
    u = db.query(User).filter(User.email == email).first()
    if not u or not verify_password(password, u.password_hash) or not u.verified:
        return RedirectResponse("/login", status_code=303)
    current_user = u

    token = create_token({"uid": u.id, "email": u.email}, expires_minutes=60*24*30)
    resp = RedirectResponse("/dashboard", status_code=303)
    resp.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=BASE_URL.startswith("https://"),
        samesite="Lax",
        max_age=60*60*24*30
    )
    return resp

@app.get("/logout")
async def logout(request: Request):
    global current_user
    current_user = None
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("session_token")
    return resp

# --- Registered audit flows ---
@app.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user:
        return RedirectResponse("/login", status_code=303)
    websites = db.query(Website).filter(Website.user_id == current_user.id).all()
    trend = {"labels": ["W1","W2","W3","W4","W5"], "values": [80, 82, 78, 85, 88]}

    last_audits = (
        db.query(Audit)
        .filter(Audit.user_id == current_user.id)
        .order_by(Audit.created_at.desc())
        .limit(5)
        .all()
    )
    if last_audits:
        avg = round(sum(a.health_score for a in last_audits) / len(last_audits))
        summary_grade = sorted([a.grade for a in last_audits])[0] if last_audits else "A"
        summary = {"grade": summary_grade, "health_score": avg}
    else:
        summary = {"grade": "A", "health_score": 88}

    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    schedule = {
        "daily_time": getattr(sub, "daily_time", "09:00"),
        "timezone": getattr(sub, "timezone", "UTC"),
        "enabled": getattr(sub, "email_schedule_enabled", False),
    }

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user,
        "websites": websites,
        "trend": trend,
        "summary": summary,
        "schedule": schedule
    })

@app.get("/audit/new")
async def new_audit_get(request: Request):
    global current_user
    if not current_user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("new_audit.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user
    })

@app.post("/audit/new")
async def new_audit_post(
    request: Request,
    url: str = Form(...),
    enable_schedule: str = Form(None),
    db: Session = Depends(get_db)
):
    global current_user
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    if not sub:
        sub = Subscription(user_id=current_user.id, plan="free", active=True, audits_used=0)
        db.add(sub); db.commit(); db.refresh(sub)

    # Free plan limit: 10 audits
    if sub.plan == "free" and sub.audits_used >= 10:
        return RedirectResponse("/dashboard", status_code=303)

    w = Website(user_id=current_user.id, url=url)
    db.add(w); db.commit(); db.refresh(w)

    if enable_schedule and hasattr(sub, "email_schedule_enabled"):
        sub.email_schedule_enabled = True
        db.commit()

    return RedirectResponse(f"/audit/run/{w.id}", status_code=303)

@app.get("/audit/run/{website_id}")
async def run_audit(website_id: int, request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user:
        return RedirectResponse("/login", status_code=303)
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    if not w:
        return RedirectResponse("/dashboard", status_code=303)

    # Perform audit (PSI-enriched + base checks)
    try:
        res = run_basic_checks(w.url)
    except Exception:
        return RedirectResponse("/dashboard", status_code=303)

    category_scores_dict = res["category_scores"]  # dict {name: score}
    overall = compute_overall(category_scores_dict)
    grade = grade_from_score(overall)
    exec_summary = summarize_200_words(w.url, category_scores_dict, res["top_issues"])

    # Store category scores as list of {name, score} for template convenience
    category_scores_list = [{"name": k, "score": int(v)} for k, v in category_scores_dict.items()]

    audit = Audit(
        user_id=current_user.id,
        website_id=w.id,
        health_score=int(overall),
        grade=grade,
        exec_summary=exec_summary,
        category_scores_json=json.dumps(category_scores_list),
        metrics_json=json.dumps(res["metrics"])
    )
    db.add(audit); db.commit(); db.refresh(audit)

    w.last_audit_at = audit.created_at
    w.last_grade = grade
    db.commit()

    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    if sub:
        sub.audits_used += 1
        db.commit()

    return RedirectResponse(f"/audit/{w.id}", status_code=303)

@app.get("/audit/{website_id}")
async def audit_detail(website_id: int, request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user:
        return RedirectResponse("/login", status_code=303)
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    if not w or not a:
        return RedirectResponse("/dashboard", status_code=303)

    # Use JSON (safer than ast.literal_eval)
    category_scores = json.loads(a.category_scores_json) if a.category_scores_json else []
    metrics = json.loads(a.metrics_json) if a.metrics_json else []

    data = {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user,
        "website": w,
        "audit": {
            "created_at": a.created_at,
            "grade": a.grade,
            "health_score": a.health_score,
            "exec_summary": a.exec_summary,
            "category_scores": category_scores,  # list of {name, score}
            "metrics": metrics
        }
    }
    return templates.TemplateResponse("audit_detail.html", data)

@app.get("/report/pdf/{website_id}")
async def report_pdf(website_id: int, request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user:
        return RedirectResponse("/login", status_code=303)
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    if not w or not a:
        return RedirectResponse("/dashboard", status_code=303)

    category_scores = json.loads(a.category_scores_json) if a.category_scores_json else []
    path = f"/tmp/certified_audit_{website_id}.pdf"

    # render_pdf accepts list or dict; we pass list for consistency
    render_pdf(path, UI_BRAND_NAME, w.url, a.grade, a.health_score, category_scores, a.exec_summary)
    return FileResponse(path, filename=f"{UI_BRAND_NAME}_Certified_Audit_{website_id}.pdf")

# ---------- Scheduling UI ----------
@app.get("/schedule")
async def schedule_get(request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user:
        return RedirectResponse("/login", status_code=303)
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    schedule = {
        "daily_time": getattr(sub, "daily_time", "09:00"),
        "timezone": getattr(sub, "timezone", "UTC"),
        "enabled": getattr(sub, "email_schedule_enabled", False),
    }
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user,
        "websites": db.query(Website).filter(Website.user_id == current_user.id).all(),
        "trend": {"labels": [], "values": []},
        "summary": {"grade": "A", "health_score": 88},
        "schedule": schedule
    })

@app.post("/schedule")
async def schedule_post(
    request: Request,
    daily_time: str = Form(...),      # "HH:MM"
    timezone: str = Form(...),        # e.g., "UTC", "Asia/Karachi"
    enabled: str = Form(None),        # "on" when checkbox ticked
    db: Session = Depends(get_db)
):
    global current_user
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    if not sub:
        sub = Subscription(user_id=current_user.id, plan="free", active=True, audits_used=0)
        db.add(sub); db.commit(); db.refresh(sub)

    # Update schedule columns
    if hasattr(sub, "daily_time"):
        sub.daily_time = daily_time
    if hasattr(sub, "timezone"):
        sub.timezone = timezone
    if hasattr(sub, "email_schedule_enabled"):
        sub.email_schedule_enabled = bool(enabled)

    db.commit()
    return RedirectResponse("/dashboard", status_code=303)

# ---------- Admin (optional) ----------
@app.get("/admin/login")
async def admin_login_get(request: Request):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user
    })

@app.post("/admin/login")
async def admin_login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    global current_user
    u = db.query(User).filter(User.email == email).first()
    if not u or not verify_password(password, u.password_hash) or not u.is_admin:
        return RedirectResponse("/admin/login", status_code=303)
    current_user = u
    token = create_token({"uid": u.id, "email": u.email, "admin": True}, expires_minutes=60*24*30)
    resp = RedirectResponse("/admin", status_code=303)
    resp.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=BASE_URL.startswith("https://"),
        samesite="Lax",
        max_age=60*60*24*30
    )
    return resp

@app.get("/admin")
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user or not current_user.is_admin:
        return RedirectResponse("/admin/login", status_code=303)
    users = db.query(User).order_by(User.created_at.desc()).limit(100).all()
    audits = db.query(Audit).order_by(Audit.created_at.desc()).limit(100).all()
    websites = db.query(Website).order_by(Website.created_at.desc()).limit(100).all()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": current_user,
        "websites": websites,
        "trend": {"labels": [], "values": []},
        "summary": {"grade": "A", "health_score": 88},
        "schedule": {"daily_time": "09:00", "timezone": "UTC", "enabled": False},
        "admin_users": users,
        "admin_audits": audits
    })

# ---------- Background Scheduler for Daily Emails ----------
def _send_report_email(to_email: str, subject: str, html_body: str) -> bool:
    """Simple SMTP email sender for scheduled reports."""
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
    """
    Checks every minute; if a user's schedule matches current time in their timezone,
    sends a daily and accumulated summary email with links to /report/pdf/{website_id}.
    """
    while True:
        try:
            db = SessionLocal()
            subs = db.query(Subscription).filter(Subscription.active == True).all()
            now_utc = datetime.utcnow()

            for sub in subs:
                # Ensure scheduling is enabled
                if not getattr(sub, "email_schedule_enabled", False):
                    continue

                tz_name   = getattr(sub, "timezone", "UTC") or "UTC"
                daily_time = getattr(sub, "daily_time", "09:00") or "09:00"

                try:
                    tz = ZoneInfo(tz_name)
                except Exception:
                    tz = ZoneInfo("UTC")

                local_now = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
                hhmm_now  = local_now.strftime("%H:%M")
                if hhmm_now != daily_time:
                    continue

                # Gather user and websites
                user = db.query(User).filter(User.id == sub.user_id).first()
                if not user or not getattr(user, "verified", False):
                    continue
                websites = db.query(Website).filter(Website.user_id == user.id).all()

                # Build HTML email safely (no unterminated string literals)
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

                    pdf_link = f"{BASE_URL}/report/pdf/{w.id}"
                    lines.append(
                        f"<p><b>{w.url}</b>: Grade <b>{last.grade}</b>, Health <b>{last.health_score}</b>/100 "
                        f"(<a href=\"{pdf_link}\" target=\"_blank\">Download Certified Report</a>)</p>"
                    )

                # Accumulated summary (last 30 days)
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

                # Plan reminder if free and at limit
                if getattr(sub, "plan", "free") == "free" and getattr(sub, "audits_used", 0) >= 10:
                    lines.append("<p><i>You've reached the free limit of 10 audits. Upgrade for $5/month to continue unlimited audits.</i></p>")

                html = "\n".join(lines)
                _send_report_email(user.email, f"{UI_BRAND_NAME} – Daily Website Audit Summary", html)

            db.close()
        except Exception:
            # keep loop resilient
            pass

        await asyncio.sleep(60)

@app.on_event("startup")
async def _start_scheduler():
    asyncio.create_task(_daily_scheduler_loop())
