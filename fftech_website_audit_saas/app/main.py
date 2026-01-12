# app/main.py
import os
import json
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Annotated

from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import Base, engine, SessionLocal
from .models import User, Website, Audit, Subscription
from .auth import hash_password, verify_password, create_token, decode_token
from .email_utils import send_verification_email, send_magic_login_email
from .audit.engine import run_basic_checks
from .audit.grader import compute_overall, grade_from_score, summarize_200_words
from .audit.report import render_pdf
from .audit.record import render_dashboard_png, export_ppt, export_xlsx

UI_BRAND_NAME = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip('/')

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

app = FastAPI(title=f"{UI_BRAND_NAME} - Certified Website Audit")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

Base.metadata.create_all(bind=engine)

# ── Startup schema patches ─────────────────────────────────────────────────────
def _ensure_schedule_columns():
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
        pass

def _ensure_user_columns():
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

# ── Dependencies ───────────────────────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_optional_current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> Optional[User]:
    token = request.cookies.get("session_token")
    if not token:
        return None
    try:
        data = decode_token(token)
        user = db.query(User).filter(User.id == data.get("uid")).first()
        if user and user.verified:
            return user
    except Exception:
        pass
    return None


def get_current_user(user: Annotated[Optional[User], Depends(get_optional_current_user)]) -> User:
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/auth/login"})
    return user


def get_admin_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=303, headers={"Location": "/auth/login"})
    return user

# ── Public ─────────────────────────────────────────────────────────────────────
@app.get("/")
async def index(
    request: Request,
    *,  # ← FIX HERE
    user: Annotated[Optional[User], Depends(get_optional_current_user)]
):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": user
    })


@app.post("/audit/open")
async def audit_open(
    request: Request,
    *,  # ← FIX HERE
    user: Annotated[Optional[User], Depends(get_optional_current_user)]
):
    form = await request.form()
    url = form.get("url")
    if not url:
        return RedirectResponse("/", status_code=303)

    normalized, res = _robust_audit(url)
    category_scores_dict = res["category_scores"]
    overall = compute_overall(category_scores_dict)
    grade = grade_from_score(overall)
    top_issues = res.get("top_issues", [])
    exec_summary = summarize_200_words(normalized, category_scores_dict, top_issues)
    category_scores_list = [{"name": k, "score": int(v)} for k, v in category_scores_dict.items()]

    return templates.TemplateResponse("audit_detail_open.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
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
        }
    })


@app.get("/report/pdf/open")
async def report_pdf_open(url: str):
    normalized, res = _robust_audit(url)
    cs_list = [{"name": k, "score": int(v)} for k, v in res["category_scores"].items()]
    overall = compute_overall(res["category_scores"])
    grade = grade_from_score(overall)
    top_issues = res.get("top_issues", [])
    exec_summary = summarize_200_words(normalized, res["category_scores"], top_issues)
    path = "/tmp/certified_audit_open.pdf"
    render_pdf(path, UI_BRAND_NAME, normalized, grade, int(overall), cs_list, exec_summary)
    return FileResponse(path, filename=f"{UI_BRAND_NAME}_Certified_Audit_Open.pdf")


@app.get("/report/png/open")
async def report_png_open(url: str):
    normalized, res = _robust_audit(url)
    cs_list = [{"name": k, "score": int(v)} for k, v in res["category_scores"].items()]
    metrics_raw = res.get("metrics", {})
    path = "/tmp/Audit_Dashboard_Open.png"
    render_dashboard_png(path, UI_BRAND_NAME, normalized, cs_list, metrics_raw)
    return FileResponse(path, filename=f"{UI_BRAND_NAME}_Audit_Dashboard_Open.png")

# ── Auth ───────────────────────────────────────────────────────────────────────
@app.get("/auth/register")
async def register_get(
    request: Request,
    *,  # ← FIX HERE
    user: Annotated[Optional[User], Depends(get_optional_current_user)]
):
    return templates.TemplateResponse("register.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": user
    })


@app.post("/auth/register")
async def register_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    *,  # ← FIX HERE
    db: Annotated[Session, Depends(get_db)]
):
    if password != confirm_password:
        return RedirectResponse("/auth/register?mismatch=1", status_code=303)
    if db.query(User).filter(User.email == email).first():
        return RedirectResponse("/auth/login?exists=1", status_code=303)
    u = User(email=email, password_hash=hash_password(password), verified=False, is_admin=False)
    db.add(u); db.commit(); db.refresh(u)
    token = create_token({"uid": u.id, "email": u.email}, expires_minutes=60*24*3)
    ok = send_verification_email(u.email, token)
    if not ok:
        print(f"[auth] Failed to send email to {u.email}. Check SMTP settings.")
    return RedirectResponse("/auth/login?check_email=1", status_code=303)


@app.get("/auth/verify")
async def verify(
    request: Request,
    token: str,
    *,  # ← FIX HERE
    db: Annotated[Session, Depends(get_db)]
):
    try:
        data = decode_token(token)
        u = db.query(User).filter(User.id == data["uid"]).first()
        if u:
            u.verified = True
            db.commit()
            return RedirectResponse("/auth/login?verified=1", status_code=303)
    except Exception:
        return templates.TemplateResponse("verify.html", {
            "request": request,
            "success": False,
            "UI_BRAND_NAME": UI_BRAND_NAME,
            "user": None
        })
    return RedirectResponse("/auth/login", status_code=303)


@app.get("/auth/login")
async def login_get(
    request: Request,
    *,  # ← FIX HERE
    user: Annotated[Optional[User], Depends(get_optional_current_user)]
):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": user
    })


@app.post("/auth/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    *,  # ← FIX HERE
    db: Annotated[Session, Depends(get_db)]
):
    u = db.query(User).filter(User.email == email).first()
    if not u or not verify_password(password, u.password_hash) or not u.verified:
        return RedirectResponse("/auth/login?error=1", status_code=303)
    token = create_token({"uid": u.id, "email": u.email}, expires_minutes=60*24*30)
    resp = RedirectResponse("/auth/dashboard", status_code=303)
    resp.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=BASE_URL.startswith("https://"),
        samesite="Lax",
        max_age=60*60*24*30
    )
    return resp


@app.get("/auth/logout")
async def logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("session_token")
    return resp


# ── Magic Login ────────────────────────────────────────────────────────────────
@app.post("/auth/magic/request")
async def magic_request(
    request: Request,
    email: str = Form(...),
    *,  # ← FIX HERE
    db: Annotated[Session, Depends(get_db)]
):
    u = db.query(User).filter(User.email == email).first()
    if not u or not u.verified:
        return RedirectResponse("/auth/login?magic_sent=1", status_code=303)
    token = create_token({"uid": u.id, "email": u.email, "type": "magic"}, expires_minutes=15)
    send_magic_login_email(u.email, token)
    return RedirectResponse("/auth/login?magic_sent=1", status_code=303)


@app.get("/auth/magic")
async def magic_login(
    request: Request,
    token: str,
    *,  # ← FIX HERE
    db: Annotated[Session, Depends(get_db)]
):
    try:
        data = decode_token(token)
        if data.get("type") != "magic":
            return RedirectResponse("/auth/login?error=1", status_code=303)
        u = db.query(User).filter(User.id == data["uid"]).first()
        if not u or not u.verified:
            return RedirectResponse("/auth/login?error=1", status_code=303)
        session_token = create_token({"uid": u.id, "email": u.email}, expires_minutes=60*24*30)
        resp = RedirectResponse("/auth/dashboard", status_code=303)
        resp.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=BASE_URL.startswith("https://"),
            samesite="Lax",
            max_age=60*60*24*30
        )
        return resp
    except Exception:
        return RedirectResponse("/auth/login?error=1", status_code=303)

# ── Other protected routes (add *, in the same way) ────────────────────────────

@app.get("/auth/dashboard")
async def dashboard(
    request: Request,
    *,  # ← FIX HERE
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)]
):
    websites = db.query(Website).filter(Website.user_id == user.id).all()
    last_audits = (
        db.query(Audit)
        .filter(Audit.user_id == user.id)
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
    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    schedule = {
        "daily_time": getattr(sub, "daily_time", "09:00"),
        "timezone": getattr(sub, "timezone", "UTC"),
        "enabled": getattr(sub, "email_schedule_enabled", False),
    }
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "user": user,
        "websites": websites,
        "trend": {"labels": trend_labels, "values": trend_values, "average": avg},
        "summary": summary,
        "schedule": schedule
    })

# Apply the same pattern (add *,) to all other routes that have both normal and Annotated parameters:
# - /auth/audit/new
# - /auth/audit/run/{website_id}
# - /auth/audit/{website_id}
# - All /auth/report/* endpoints
# - Admin routes
# etc.

# ── Scheduler (unchanged) ──────────────────────────────────────────────────────
async def _daily_scheduler_loop():
    while True:
        try:
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
                    "<p>Here is your daily summary. Download certified reports via the links below.</p>",
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
                        f"<p><b>{w.url}</b>: Grade <b>{last.grade}</b>, "
                        f"Health <b>{last.health_score}</b>/100 "
                        f"(<a href=\"{pdf_link}\" target=\"_blank\" rel=\"noopener noreferrer\">Certified PDF</a>)</p>"
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
                # _send_report_email(...)  # your existing function
            db.close()
        except Exception:
            pass
        await asyncio.sleep(60)


@app.on_event("startup")
async def _start_scheduler():
    asyncio.create_task(_daily_scheduler_loop())
