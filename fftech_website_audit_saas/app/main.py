import os, json, asyncio
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
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

UI_BRAND_NAME = os.getenv('UI_BRAND_NAME', 'FF Tech')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')
SMTP_HOST = os.getenv('SMTP_HOST')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')

app = FastAPI()
app.mount('/static', StaticFiles(directory='app/static'), name='static')
templates = Jinja2Templates(directory='app/templates')
Base.metadata.create_all(bind=engine)

# ensure columns exist (works on Postgres; ignored if SQLite)

def _ensure_schedule_columns():
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS daily_time VARCHAR(8) DEFAULT '09:00';
            """))
            conn.execute(text("""
                ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) DEFAULT 'UTC';
            """))
            conn.execute(text("""
                ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS email_schedule_enabled BOOLEAN DEFAULT FALSE;
            """))
            conn.commit()
    except Exception:
        pass


def _ensure_user_columns():
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT FALSE;
            """))
            conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;
            """))
            conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
            """))
            conn.commit()
    except Exception:
        pass

_ensure_schedule_columns()
_ensure_user_columns()

# DB dependency

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Simple session (note: global for demo; move to request.state/session in production)
current_user = None

@app.middleware('http')
async def session_middleware(request: Request, call_next):
    global current_user
    try:
        token = request.cookies.get('session_token')
        if token:
            data = decode_token(token)
            uid = data.get('uid')
            if uid:
                db = SessionLocal()
                try:
                    u = db.query(User).filter(User.id == uid).first()
                    if u and getattr(u, 'verified', False):
                        current_user = u
                finally:
                    db.close()
    except Exception:
        pass
    response = await call_next(request)
    return response

@app.get('/')
async def index(request: Request):
    return templates.TemplateResponse('index.html', {
        'request': request,
        'UI_BRAND_NAME': UI_BRAND_NAME,
        'user': current_user
    })

@app.post('/audit/open')
async def audit_open(request: Request):
    form = await request.form()
    url = form.get('url')
    if not url:
        return RedirectResponse('/', status_code=303)
    res = run_basic_checks(url)
    category_scores_dict = res['category_scores']
    overall = compute_overall(category_scores_dict)
    grade = grade_from_score(overall)
    exec_summary = summarize_200_words(url, category_scores_dict, res['top_issues'])
    category_scores_list = [{'name': k, 'score': int(v)} for k, v in category_scores_dict.items()]
    return templates.TemplateResponse('audit_detail_open.html', {
        'request': request,
        'UI_BRAND_NAME': UI_BRAND_NAME,
        'user': current_user,
        'website': {'id': None, 'url': url},
        'audit': {
            'created_at': datetime.utcnow(),
            'grade': grade,
            'health_score': int(overall),
            'exec_summary': exec_summary,
            'category_scores': category_scores_list,
            'metrics': res['metrics'],
            'top_issues': res['top_issues'],
        }
    })

@app.get('/report/pdf/open')
async def report_pdf_open(url: str):
    res = run_basic_checks(url)
    cs_list = [{'name': k, 'score': int(v)} for k, v in res['category_scores'].items()]
    overall = compute_overall(res['category_scores'])
    grade = grade_from_score(overall)
    exec_summary = summarize_200_words(url, res['category_scores'], res['top_issues'])
    path = '/tmp/certified_audit_open.pdf'
    render_pdf(path, UI_BRAND_NAME, url, grade, int(overall), cs_list, exec_summary)
    return FileResponse(path, filename=f"{UI_BRAND_NAME}_Certified_Audit_Open.pdf")

@app.get('/auth/register')
async def register_get(request: Request):
    return templates.TemplateResponse('register.html', {
        'request': request,
        'UI_BRAND_NAME': UI_BRAND_NAME,
        'user': current_user
    })

@app.post('/auth/register')
async def register_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    if password != confirm_password:
        return RedirectResponse('/auth/register?mismatch=1', status_code=303)
    if db.query(User).filter(User.email == email).first():
        return RedirectResponse('/auth/login?exists=1', status_code=303)
    u = User(email=email, password_hash=hash_password(password), verified=False, is_admin=False)
    db.add(u); db.commit(); db.refresh(u)
    token = create_token({'uid': u.id, 'email': u.email}, expires_minutes=60*24*3)
    try:
        send_verification_email(u.email, token)
    except Exception:
        pass
    return RedirectResponse('/auth/login?check_email=1', status_code=303)

@app.get('/auth/verify')
async def verify(request: Request, token: str, db: Session = Depends(get_db)):
    try:
        data = decode_token(token)
        u = db.query(User).filter(User.id == data['uid']).first()
        if u:
            u.verified = True
            db.commit()
            return RedirectResponse('/auth/login?verified=1', status_code=303)
    except Exception:
        return templates.TemplateResponse('verify.html', {
            'request': request,
            'success': False,
            'UI_BRAND_NAME': UI_BRAND_NAME,
            'user': current_user
        })
    return RedirectResponse('/auth/login', status_code=303)

@app.get('/auth/login')
async def login_get(request: Request):
    return templates.TemplateResponse('login.html', {
        'request': request,
        'UI_BRAND_NAME': UI_BRAND_NAME,
        'user': current_user
    })

@app.post('/auth/login')
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    global current_user
    u = db.query(User).filter(User.email == email).first()
    if not u or not verify_password(password, u.password_hash) or not u.verified:
        return RedirectResponse('/auth/login?error=1', status_code=303)
    current_user = u
    token = create_token({'uid': u.id, 'email': u.email}, expires_minutes=60*24*30)
    resp = RedirectResponse('/auth/dashboard', status_code=303)
    resp.set_cookie(
        key='session_token',
        value=token,
        httponly=True,
        secure=BASE_URL.startswith('https://'),
        samesite='Lax',
        max_age=60*60*24*30
    )
    return resp

@app.get('/auth/logout')
async def logout(request: Request):
    global current_user
    current_user = None
    resp = RedirectResponse('/', status_code=303)
    resp.delete_cookie('session_token')
    return resp

@app.get('/auth/dashboard')
async def dashboard(request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user:
        return RedirectResponse('/auth/login', status_code=303)
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
        'grade': (last_audits[0].grade if last_audits else 'A'),
        'health_score': (last_audits[0].health_score if last_audits else 88)
    }
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    schedule = {
        'daily_time': getattr(sub, 'daily_time', '09:00'),
        'timezone': getattr(sub, 'timezone', 'UTC'),
        'enabled': getattr(sub, 'email_schedule_enabled', False),
    }
    return templates.TemplateResponse('dashboard.html', {
        'request': request,
        'UI_BRAND_NAME': UI_BRAND_NAME,
        'user': current_user,
        'websites': websites,
        'trend': {'labels': trend_labels, 'values': trend_values, 'average': avg},
        'summary': summary,
        'schedule': schedule
    })

@app.get('/auth/audit/new')
async def new_audit_get(request: Request):
    global current_user
    if not current_user:
        return RedirectResponse('/auth/login', status_code=303)
    return templates.TemplateResponse('new_audit.html', {
        'request': request,
        'UI_BRAND_NAME': UI_BRAND_NAME,
        'user': current_user
    })

@app.post('/auth/audit/new')
async def new_audit_post(
    request: Request,
    url: str = Form(...),
    enable_schedule: str = Form(None),
    db: Session = Depends(get_db)
):
    global current_user
    if not current_user:
        return RedirectResponse('/auth/login', status_code=303)
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    if not sub:
        sub = Subscription(user_id=current_user.id, plan='free', active=True, audits_used=0)
        db.add(sub); db.commit(); db.refresh(sub)
    if enable_schedule and hasattr(sub, 'email_schedule_enabled'):
        sub.email_schedule_enabled = True
        db.commit()
    w = Website(user_id=current_user.id, url=url)
    db.add(w); db.commit(); db.refresh(w)
    return RedirectResponse(f'/auth/audit/run/{w.id}', status_code=303)

@app.get('/auth/audit/run/{website_id}')
async def run_audit(website_id: int, request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user:
        return RedirectResponse('/auth/login', status_code=303)
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    if not w:
        return RedirectResponse('/auth/dashboard', status_code=303)
    try:
        res = run_basic_checks(w.url)
    except Exception:
        return RedirectResponse('/auth/dashboard', status_code=303)
    category_scores_dict = res['category_scores']
    overall = compute_overall(category_scores_dict)
    grade = grade_from_score(overall)
    exec_summary = summarize_200_words(w.url, category_scores_dict, res['top_issues'])
    category_scores_list = [{'name': k, 'score': int(v)} for k, v in category_scores_dict.items()]
    audit = Audit(
        user_id=current_user.id,
        website_id=w.id,
        health_score=int(overall),
        grade=grade,
        exec_summary=exec_summary,
        category_scores_json=json.dumps(category_scores_list),
        metrics_json=json.dumps(res['metrics'])
    )
    db.add(audit); db.commit(); db.refresh(audit)
    w.last_audit_at = audit.created_at
    w.last_grade = grade
    db.commit()
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    if sub:
        sub.audits_used = (sub.audits_used or 0) + 1
        db.commit()
    return RedirectResponse(f'/auth/audit/{w.id}', status_code=303)

@app.get('/auth/audit/{website_id}')
async def audit_detail(website_id: int, request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user:
        return RedirectResponse('/auth/login', status_code=303)
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    if not w or not a:
        return RedirectResponse('/auth/dashboard', status_code=303)
    category_scores = json.loads(a.category_scores_json) if a.category_scores_json else []
    metrics = json.loads(a.metrics_json) if a.metrics_json else []
    return templates.TemplateResponse('audit_detail.html', {
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
            'metrics': metrics,
        }
    })

@app.get('/auth/report/pdf/{website_id}')
async def report_pdf(website_id: int, request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user:
        return RedirectResponse('/auth/login', status_code=303)
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    if not w or not a:
        return RedirectResponse('/auth/dashboard', status_code=303)
    category_scores = json.loads(a.category_scores_json) if a.category_scores_json else []
    path = f"/tmp/certified_audit_{website_id}.pdf"
    render_pdf(path, UI_BRAND_NAME, w.url, a.grade, a.health_score, category_scores, a.exec_summary)
    return FileResponse(path, filename=f"{UI_BRAND_NAME}_Certified_Audit_{website_id}.pdf")

# Minimal scheduler sending daily summary (optional)

def _send_report_email(to_email: str, subject: str, html_body: str) -> bool:
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
    while True:
        try:
            db = SessionLocal()
            subs = db.query(Subscription).filter(Subscription.active == True).all()
            now_utc = datetime.utcnow()
            for sub in subs:
                if not getattr(sub, 'email_schedule_enabled', False):
                    continue
                tz_name = getattr(sub, 'timezone', 'UTC') or 'UTC'
                daily_time = getattr(sub, 'daily_time', '09:00') or '09:00'
                try:
                    tz = ZoneInfo(tz_name)
                except Exception:
                    tz = ZoneInfo('UTC')
                local_now = now_utc.replace(tzinfo=ZoneInfo('UTC')).astimezone(tz)
                hhmm_now = local_now.strftime('%H:%M')
                if hhmm_now != daily_time:
                    continue
                user = db.query(User).filter(User.id == sub.user_id).first()
                if not user or not getattr(user, 'verified', False):
                    continue
                websites = db.query(Website).filter(Website.user_id == user.id).all()
                lines = [
                    f"<h3>Daily Website Audit Summary — {UI_BRAND_NAME}</h3>",
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
                    pdf_link = f"{BASE_URL}/auth/report/pdf/{w.id}"
                    lines.append(
                        f"<p><b>{w.url}</b>: Grade <b>{last.grade}</b>, Health <b>{last.health_score}</b>/100 "
                        f"(<a href="{pdf_link}" target="_blank" rel="noopener noreferrer">Download Certified Report</a>)</p>"
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
                html = "
".join(lines)
                _send_report_email(user.email, f"{UI_BRAND_NAME} — Daily Website Audit Summary", html)
            db.close()
        except Exception:
            pass
        await asyncio.sleep(60)

@app.on_event('startup')
async def _start_scheduler():
    asyncio.create_task(_daily_scheduler_loop())
