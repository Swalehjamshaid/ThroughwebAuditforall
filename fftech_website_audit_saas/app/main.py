
# fftech_website_audit_saas/app/main.py
import os
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

# For sending scheduled emails (we keep verification in email_utils.py)
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

UI_BRAND_NAME = os.getenv('UI_BRAND_NAME', 'FF Tech')

SMTP_HOST = os.getenv('SMTP_HOST')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')

# App & templates
app = FastAPI()
app.mount('/static', StaticFiles(directory='app/static'), name='static')
templates = Jinja2Templates(directory='app/templates')

# Ensure DB tables exist
Base.metadata.create_all(bind=engine)

# ---- Railway-friendly startup tweaks ----
# Add schedule columns to subscriptions table (non-breaking)
def _ensure_schedule_columns():
    try:
        with engine.connect() as conn:
            # Postgres friendly "IF NOT EXISTS" additions
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
        # Silent: do not break app if schema change fails
        pass

_ensure_schedule_columns()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Simple session management (placeholder) + JWT cookie enhancement
current_user = None

@app.middleware("http")
async def session_middleware(request: Request, call_next):
    """
    Preserve global current_user behavior, but also hydrate it from a signed cookie if present.
    This does not change links or query parameters.
    """
    global current_user
    if current_user is None:
        token = request.cookies.get("session_token")
        if token:
            try:
                data = decode_token(token)
                uid = data.get("uid")
                if uid:
                    # Open a short-lived session to fetch the user
                    db = SessionLocal()
                    try:
                        u = db.query(User).filter(User.id == uid).first()
                        if u and u.verified:
                            current_user = u
                    finally:
                        db.close()
            except Exception:
                # ignore token errors
                pass
    response = await call_next(request)
    return response

# ---------- Core routes (UNCHANGED) ----------

@app.get('/')
async def index(request: Request):
    return templates.TemplateResponse('index.html', {
        'request': request,
        'UI_BRAND_NAME': UI_BRAND_NAME,
        'user': current_user
    })

@app.get('/register')
async def register_get(request: Request):
    return templates.TemplateResponse('register.html', {
        'request': request,
        'UI_BRAND_NAME': UI_BRAND_NAME,
        'user': current_user
    })

@app.post('/register')
async def register_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    if password != confirm_password:
        return RedirectResponse('/register', status_code=303)
    if db.query(User).filter(User.email == email).first():
        return RedirectResponse('/login', status_code=303)
    u = User(email=email, password_hash=hash_password(password), verified=False, is_admin=False)
    db.add(u); db.commit(); db.refresh(u)
    token = create_token({'uid': u.id, 'email': u.email}, expires_minutes=60*24*3)
    try:
        send_verification_email(u.email, token)
    except Exception:
        # Email failures should not block registration
        pass
    return RedirectResponse('/login', status_code=303)

@app.get('/verify')
async def verify(request: Request, token: str, db: Session = Depends(get_db)):
    success = False
    try:
        data = decode_token(token)
        u = db.query(User).filter(User.id == data['uid']).first()
        if u:
            u.verified = True
            db.commit()
            success = True
    except Exception:
        success = False
    return templates.TemplateResponse('verify.html', {
        'request': request,
        'success': success,
        'UI_BRAND_NAME': UI_BRAND_NAME,
        'user': current_user
    })

@app.get('/login')
async def login_get(request: Request):
    return templates.TemplateResponse('login.html', {
        'request': request,
        'UI_BRAND_NAME': UI_BRAND_NAME,
        'user': current_user
    })

@app.post('/login')
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    global current_user
    u = db.query(User).filter(User.email == email).first()
    if not u or not verify_password(password, u.password_hash) or not u.verified:
        return RedirectResponse('/login', status_code=303)
    current_user = u

    # Set a JWT session cookie silently (HttpOnly; preserves existing link behavior)
    token = create_token({'uid': u.id, 'email': u.email}, expires_minutes=60*24*30)
    resp = RedirectResponse('/dashboard', status_code=303)
    # Secure cookie flags: HttpOnly; Secure depends on BASE_URL scheme
    resp.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=BASE_URL.startswith("https://"),
        samesite="Lax",
        max_age=60*60*24*30
    )
    return resp

@app.get('/logout')
async def logout(request: Request):
    global current_user
    current_user = None
    resp = RedirectResponse('/', status_code=303)
    resp.delete_cookie("session_token")
    return resp

@app.get('/dashboard')
async def dashboard(request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user:
        return RedirectResponse('/login', status_code=303)
    websites = db.query(Website).filter(Website.user_id == current_user.id).all()
    # Simple trend placeholders (unchanged)
    trend = {'labels': ["W1","W2","W3","W4","W5"], 'values': [80, 82, 78, 85, 88]}

    # Compute last audit summary for user
    last_audits = (
        db.query(Audit)
        .filter(Audit.user_id == current_user.id)
        .order_by(Audit.created_at.desc())
        .limit(5)
        .all()
    )
    if last_audits:
        avg = round(sum(a.health_score for a in last_audits) / len(last_audits))
        # Select best grade among last audits
        summary_grade = sorted([a.grade for a in last_audits])[0] if last_audits else 'A'
        summary = {'grade': summary_grade, 'health_score': avg}
    else:
        summary = {'grade': 'A', 'health_score': 88}

    # Read schedule info from subscriptions (added columns on startup)
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    schedule = {
        'daily_time': (sub.daily_time if hasattr(sub, 'daily_time') else '09:00'),
        'timezone': (sub.timezone if hasattr(sub, 'timezone') else 'UTC'),
        'enabled': (sub.email_schedule_enabled if hasattr(sub, 'email_schedule_enabled') else False)
    }

    return templates.TemplateResponse('dashboard.html', {
        'request': request,
        'UI_BRAND_NAME': UI_BRAND_NAME,
        'user': current_user,
        'websites': websites,
        'trend': trend,
        'summary': summary,
        'schedule': schedule
    })

@app.get('/audit/new')
async def new_audit_get(request: Request):
    global current_user
    if not current_user:
        return RedirectResponse('/login', status_code=303)
    return templates.TemplateResponse('new_audit.html', {
        'request': request,
        'UI_BRAND_NAME': UI_BRAND_NAME,
        'user': current_user
    })

@app.post('/audit/new')
async def new_audit_post(
    request: Request,
    url: str = Form(...),
    enable_schedule: str = Form(None),
    db: Session = Depends(get_db)
):
    global current_user
    if not current_user:
        return RedirectResponse('/login', status_code=303)
    # Subscription limit
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    if not sub:
        sub = Subscription(user_id=current_user.id, plan='free', active=True, audits_used=0)
        db.add(sub); db.commit(); db.refresh(sub)
    # Preserve original behavior and fix HTML-escaped operator
    if sub.plan == 'free' and sub.audits_used >= 10:
        # (Optional) You can show a banner on dashboard urging $5/month upgrade
        return RedirectResponse('/dashboard', status_code=303)
    w = Website(user_id=current_user.id, url=url)
    db.add(w); db.commit(); db.refresh(w)

    # If user ticked schedule (non-breaking addition)
    if enable_schedule and hasattr(sub, 'email_schedule_enabled'):
        sub.email_schedule_enabled = True
        db.commit()

    return RedirectResponse(f'/audit/run/{w.id}', status_code=303)

@app.get('/audit/run/{website_id}')
async def run_audit(website_id: int, request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user:
        return RedirectResponse('/login', status_code=303)
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    if not w:
        return RedirectResponse('/dashboard', status_code=303)
    try:
        res = run_basic_checks(w.url)
    except Exception:
        return RedirectResponse('/dashboard', status_code=303)

    category_scores = res['category_scores']
    overall = compute_overall(category_scores)
    grade = grade_from_score(overall)
    exec_summary = summarize_200_words(w.url, category_scores, res['top_issues'])

    audit = Audit(
        user_id=current_user.id,
        website_id=w.id,
        health_score=int(overall),
        grade=grade,
        exec_summary=exec_summary,
        category_scores_json=str([{'name':k,'score':int(v)} for k,v in category_scores.items()]),
        metrics_json=str(res['metrics'])
    )
    db.add(audit); db.commit(); db.refresh(audit)

    w.last_audit_at = audit.created_at
    w.last_grade = grade
    db.commit()

    # increment subscription usage
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    if sub:
        sub.audits_used += 1
        db.commit()
    return RedirectResponse(f'/audit/{w.id}', status_code=303)

@app.get('/audit/{website_id}')
async def audit_detail(website_id: int, request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user:
        return RedirectResponse('/login', status_code=303)
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    if not w or not a:
        return RedirectResponse('/dashboard', status_code=303)
    import ast
    category_scores = ast.literal_eval(a.category_scores_json)
    metrics = ast.literal_eval(a.metrics_json)
    data = {
        'request': request,
        'UI_BRAND_NAME': UI_BRAND_NAME,
        'user': current_user,
        'website': w,
        'audit': {
            'created_at': a.created_at,
            'grade': a.grade,
            'health_score': a.health_score,
            'exec_summary': a.exec_summary,
            'category_scores': category_scores,
            'metrics': metrics
        }
    }
    return templates.TemplateResponse('audit_detail.html', data)

@app.get('/report/pdf/{website_id}')
async def report_pdf(website_id: int, request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user:
        return RedirectResponse('/login', status_code=303)
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    if not w or not a:
        return RedirectResponse('/dashboard', status_code=303)
    import ast
    category_scores = ast.literal_eval(a.category_scores_json)
    path = f"/tmp/certified_audit_{website_id}.pdf"
    render_pdf(path, UI_BRAND_NAME, w.url, a.grade, a.health_score, category_scores, a.exec_summary)
    return FileResponse(path, filename=f"{UI_BRAND_NAME}_Certified_Audit_{website_id}.pdf")

# ---------- NEW OPTIONAL ROUTES (do not disturb existing ones) ----------

@app.get('/schedule')
async def schedule_get(request: Request, db: Session = Depends(get_db)):
    """User schedule settings page (optional UI integration)."""
    global current_user
    if not current_user:
        return RedirectResponse('/login', status_code=303)
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    schedule = {
        'daily_time': (sub.daily_time if hasattr(sub, 'daily_time') else '09:00'),
        'timezone': (sub.timezone if hasattr(sub, 'timezone') else 'UTC'),
        'enabled': (sub.email_schedule_enabled if hasattr(sub, 'email_schedule_enabled') else False)
    }
    # Reuse dashboard template or create a dedicated schedule.html
    return templates.TemplateResponse('dashboard.html', {
        'request': request,
        'UI_BRAND_NAME': UI_BRAND_NAME,
        'user': current_user,
        'websites': db.query(Website).filter(Website.user_id == current_user.id).all(),
        'trend': {'labels': [], 'values': []},
        'summary': {'grade': 'A', 'health_score': 88},
        'schedule': schedule
    })

@app.post('/schedule')
async def schedule_post(
    request: Request,
    daily_time: str = Form(...),      # "HH:MM" in 24h format
    timezone: str = Form(...),        # e.g., "UTC", "Asia/Karachi"
    enabled: str = Form(None),        # "on" when checkbox ticked
    db: Session = Depends(get_db)
):
    global current_user
    if not current_user:
        return RedirectResponse('/login', status_code=303)

    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    if not sub:
        sub = Subscription(user_id=current_user.id, plan='free', active=True, audits_used=0)
        db.add(sub); db.commit(); db.refresh(sub)

    # Update schedule columns (added on startup)
    if hasattr(sub, 'daily_time'):
        sub.daily_time = daily_time
    if hasattr(sub, 'timezone'):
        sub.timezone = timezone
    if hasattr(sub, 'email_schedule_enabled'):
        sub.email_schedule_enabled = bool(enabled)

    db.commit()
    return RedirectResponse('/dashboard', status_code=303)

# ---------- Admin Area (optional, world-class ops) ----------

@app.get('/admin/login')
async def admin_login_get(request: Request):
    return templates.TemplateResponse('login.html', {
        'request': request,
        'UI_BRAND_NAME': UI_BRAND_NAME,
        'user': current_user
    })

@app.post('/admin/login')
async def admin_login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    global current_user
    u = db.query(User).filter(User.email == email).first()
    if not u or not verify_password(password, u.password_hash) or not u.is_admin:
        return RedirectResponse('/admin/login', status_code=303)
    current_user = u
    token = create_token({'uid': u.id, 'email': u.email, 'admin': True}, expires_minutes=60*24*30)
    resp = RedirectResponse('/admin', status_code=303)
    resp.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=BASE_URL.startswith("https://"),
        samesite="Lax",
        max_age=60*60*24*30
    )
    return resp

@app.get('/admin')
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user or not current_user.is_admin:
        return RedirectResponse('/admin/login', status_code=303)
    users = db.query(User).order_by(User.created_at.desc()).limit(100).all()
    audits = db.query(Audit).order_by(Audit.created_at.desc()).limit(100).all()
    websites = db.query(Website).order_by(Website.created_at.desc()).limit(100).all()
    # Use a generic admin template or reuse dashboard with admin flag
    return templates.TemplateResponse('dashboard.html', {
        'request': request,
        'UI_BRAND_NAME': UI_BRAND_NAME,
        'user': current_user,
        'websites': websites,
        'trend': {'labels': [], 'values': []},
        'summary': {'grade': 'A', 'health_score': 88},
        'schedule': {'daily_time': '09:00', 'timezone': 'UTC', 'enabled': False},
        # You can use the template to conditionally render admin sections
        'admin_users': users,
        'admin_audits': audits
    })

@app.get('/admin/users')
async def admin_users(request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user or not current_user.is_admin:
        return RedirectResponse('/admin/login', status_code=303)
    users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse('dashboard.html', {
        'request': request,
        'UI_BRAND_NAME': UI_BRAND_NAME,
        'user': current_user,
        'websites': db.query(Website).order_by(Website.created_at.desc()).limit(100).all(),
        'trend': {'labels': [], 'values': []},
        'summary': {'grade': 'A', 'health_score': 88},
        'schedule': {'daily_time': '09:00', 'timezone': 'UTC', 'enabled': False},
        'admin_users': users,
        'admin_audits': db.query(Audit).order_by(Audit.created_at.desc()).limit(100).all()
    })

@app.get('/admin/audits')
async def admin_audits(request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user or not current_user.is_admin:
        return RedirectResponse('/admin/login', status_code=303)
    audits = db.query(Audit).order_by(Audit.created_at.desc()).all()
    return templates.TemplateResponse('dashboard.html', {
        'request': request,
        'UI_BRAND_NAME': UI_BRAND_NAME,
        'user': current_user,
        'websites': db.query(Website).order_by(Website.created_at.desc()).limit(100).all(),
        'trend': {'labels': [], 'values': []},
        'summary': {'grade': 'A', 'health_score': 88},
        'schedule': {'daily_time': '09:00', 'timezone': 'UTC', 'enabled': False},
        'admin_users': db.query(User).order_by(User.created_at.desc()).limit(100).all(),
        'admin_audits': audits
    })

# ---------- Background Scheduler for Daily Emails ----------

def _send_report_email(to_email: str, subject: str, html_body: str):
    """
    Simple SMTP email sender for scheduled reports.
    Uses the same env vars as email_utils.py; keeps verification separate.
    """
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        return False
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = SMTP_USER
    msg['To'] = to_email
    msg.attach(MIMEText(html_body, 'html'))
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
    sends a daily and accumulated summary email.

    This does not change any existing routes or links; it only emails summaries with
    links to existing /report/pdf/{website_id}.
    """
    # Avoid tight loop, run forever
    while True:
        try:
            db = SessionLocal()
            subs = db.query(Subscription).filter(Subscription.active == True).all()
            now_utc = datetime.utcnow()
            for sub in subs:
                # Ensure columns exist and scheduling is enabled
                if not hasattr(sub, 'email_schedule_enabled') or not sub.email_schedule_enabled:
                    continue
                tz_name = getattr(sub, 'timezone', 'UTC') or 'UTC'
                daily_time = getattr(sub, 'daily_time', '09:00') or '09:00'

                try:
                    tz = ZoneInfo(tz_name)
                except Exception:
                    tz = ZoneInfo('UTC')

                local_now = now_utc.replace(tzinfo=ZoneInfo('UTC')).astimezone(tz)
                hhmm_now = local_now.strftime("%H:%M")
                if hhmm_now != daily_time:
                    continue  # not time yet

                # Gather user, websites & last audits
                user = db.query(User).filter(User.id == sub.user_id).first()
                if not user or not user.verified:
                    continue
                websites = db.query(Website).filter(Website.user_id == user.id).all()

                # Build daily summary for each site (last audit)
                lines = [f"<h3>Daily Website Audit Summary – {UI_BRAND_NAME}</h3>"]
                lines.append(f"<p>Hello, {user.email}!</p>")
                lines.append("<p>Here is your daily summary. Download certified PDFs via links below.</p>")
                for w in websites:
                    last = db.query(Audit).filter(Audit.website_id == w.id).order_by(Audit.created_at.desc()).first()
                    if not last:
                        lines.append(f"<p><b>{w.url}</b>: No audits yet.</p>")
                        continue
                    pdf_link = f"{BASE_URL}/report/pdf/{w.id}"
                    lines.append(
                        f"<p><b>{w.url}</b>: Grade <b>{last.grade}</b>, Health <b>{last.health_score}</b>/100 "
                        f"({pdf_link}Download Certified Report</a>)</p>"
                    )

                # Accumulated summary (last 30 days average)
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

                # Plan reminder if free plan and reached the limit
                if sub.plan == 'free' and sub.audits_used >= 10:
                    lines.append("<p><i>You’ve reached the free limit of 10 audits. Upgrade for $5/month to continue unlimited audits.</i></p>")

                html = "\n".join(lines)
                _send_report_email(user.email, f"{UI_BRAND_NAME} – Daily Website Audit Summary", html)
            db.close()
        except Exception:
            # don't crash loop
            pass
        # Sleep ~60s
        await asyncio.sleep(60)

@app.on_event("startup")
async def _start_scheduler():
    # Launch background loop for scheduled emails
    asyncio.create_task(_daily_scheduler_loop())
