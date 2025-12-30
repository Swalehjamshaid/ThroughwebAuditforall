
import os, json, traceback, datetime, logging
from typing import Dict, Any, List

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Form, Body
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .audit_engine import AuditEngine, METRIC_DESCRIPTORS, grade_from_score
from .db import SessionLocal, Base, engine, User, Audit, Schedule
from .auth_email import send_verification_link, verify_magic_or_verify_link, verify_session_token, generate_token, send_email_with_pdf
from .ui_and_pdf import build_pdf_report
from .db_migration import migrate_schedules_table

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('fftech')
ENABLE_AUTH = (os.getenv('ENABLE_AUTH', 'true').lower() == 'true')

app = FastAPI(title='FF Tech AI • Website Audit SaaS', version='9.0')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

ROOT_STATIC = os.path.join(os.path.dirname(__file__), '..', 'static')
PKG_STATIC  = os.path.join(os.path.dirname(__file__), 'static')
STATIC_DIR  = ROOT_STATIC if os.path.isdir(ROOT_STATIC) else PKG_STATIC
app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates')
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# DB init safe
def init_db():
    try:
        with engine.connect() as _:
            pass
        Base.metadata.create_all(bind=engine)
        migrate_schedules_table(engine)
        logger.info('DB initialization complete ✅')
    except Exception as e:
        logger.error('DB initialization failed: %s', e)

@app.get('/health')
def health():
    return {'status': 'ok', 'time': datetime.datetime.utcnow().isoformat()}

# Landing (two options: Open Audit / Registration)
@app.get('/', response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse('landing.html', { 'request': request, 'ENABLE_AUTH': ENABLE_AUTH })

# Open Audit (form POST)
@app.post('/audit/open', response_class=HTMLResponse)
def audit_open(request: Request, url: str = Form(...)):
    url = (url or '').strip()
    logger.info('[/audit/open] URL=%s', url)
    if not url.lower().startswith(('http://','https://')):
        return templates.TemplateResponse('landing.html', { 'request': request, 'ENABLE_AUTH': ENABLE_AUTH, 'error': 'Invalid URL (must start with http:// or https://)' }, status_code=400)
    try:
        eng = AuditEngine(url)
        metrics = eng.compute_metrics()
        logger.info('[/audit/open] Metrics OK (%d keys)', len(metrics))
    except Exception as e:
        logger.error('[/audit/open] Audit failed: %s', e)
        traceback.print_exc()
        return templates.TemplateResponse('landing.html', { 'request': request, 'ENABLE_AUTH': ENABLE_AUTH, 'error': f'Audit failed: {e}' }, status_code=500)

    # Read primitives
    score = float(metrics.get(1, {}).get('value', 0.0))
    grade = metrics.get(2, {}).get('value', grade_from_score(score))
    breakdown = metrics.get(8, {}).get('value', {})

    # Progress values for UI
    ctx_progress = {
        'progress_overall': max(0.0, min(100.0, score)),
        'progress_security': float(breakdown.get('security', 0)),
        'progress_performance': float(breakdown.get('performance', 0)),
        'progress_seo': float(breakdown.get('seo', 0)),
        'progress_mobile': float(breakdown.get('mobile', 0)),
        'progress_content': float(breakdown.get('content', 0)),
    }

    # Build rows 1..200
    rows: List[Dict[str, Any]] = []
    for mid in range(1, 201):
        desc = METRIC_DESCRIPTORS.get(mid, { 'name': f'Metric {mid}', 'category': '-' })
        val  = metrics.get(mid, { 'value': 'N/A' })['value']
        if isinstance(val, (dict, list)):
            try:
                val = json.dumps(val, ensure_ascii=False)
            except Exception:
                val = str(val)
        rows.append({ 'id': mid, 'name': desc['name'], 'category': desc['category'], 'value': val })

    ctx = {
        'request': request,
        'ENABLE_AUTH': ENABLE_AUTH,
        'url_display': url,
        'score': score,
        'grade': grade,
        'category_breakdown': breakdown,
        'rows': rows,
        **ctx_progress,
    }
    return templates.TemplateResponse('results.html', ctx)

# Registration
@app.get('/auth/register', response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse('register.html', { 'request': request, 'ENABLE_AUTH': ENABLE_AUTH })

@app.post('/auth/register', response_class=HTMLResponse)
def auth_register(request: Request, email: str = Form(...), name: str = Form('User')):
    email = (email or '').strip().lower()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(name=name.strip() or 'User', email=email, plan='free', is_verified=False)
            db.add(user); db.commit()
        send_verification_link(email)
        return templates.TemplateResponse('register_done.html', { 'request': request, 'ENABLE_AUTH': ENABLE_AUTH, 'email': email })
    finally:
        db.close()

@app.get('/auth/verify-link', response_class=HTMLResponse)
def auth_verify_link(request: Request, token: str):
    email = verify_magic_or_verify_link(token)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return templates.TemplateResponse('landing.html', { 'request': request, 'ENABLE_AUTH': ENABLE_AUTH, 'error': 'User not found' }, status_code=404)
        user.is_verified = True; db.commit()
        session_token = generate_token({ 'email': email, 'purpose': 'session' })
        return templates.TemplateResponse('verify_success.html', { 'request': request, 'ENABLE_AUTH': ENABLE_AUTH, 'message': 'Verification successful.', 'token': session_token })
    finally:
        db.close()

# Download 5-page PDF (registered)
@app.get('/download/pdf')
def download_pdf(token: str, url: str):
    data = verify_session_token(token)
    email = data.get('email')
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user or not user.is_verified:
            return JSONResponse({ 'detail': 'Email not verified' }, status_code=403)
        audit = Audit(user_id=user.id, url=url, metrics_json='{}', score=0, grade='A')
        categories = { 'security': 80, 'performance': 75, 'seo': 78, 'mobile': 72, 'content': 76 }
        strengths, weaknesses, fixes = ['HTTPS active','CSP present'], ['Mixed content'], ['Fix mixed content']
        pdf_bytes = build_pdf_report(audit, categories, strengths, weaknesses, fixes)
        send_email_with_pdf(user.email, 'Your FF Tech Audit Report', 'Attached is your 5-page audit report.', pdf_bytes)
        return StreamingResponse(
            io.BytesIO(pdf_bytes), media_type='application/pdf',
            headers={'Content-Disposition': 'attachment; filename="FFTech_Audit_Report.pdf"'}
        )
    finally:
        db.close()

# Schedule UI page
@app.get('/schedule', response_class=HTMLResponse)
def schedule_page(request: Request):
    return templates.TemplateResponse('schedule.html', { 'request': request, 'ENABLE_AUTH': ENABLE_AUTH })

# Schedule API
@app.post('/schedule/set')
def schedule_set(req: Dict[str, str] = Body(...)):
    token = (req.get('token') or '').strip()
    url = (req.get('url') or '').strip()
    frequency = (req.get('frequency') or 'weekly').lower()  # daily/weekly/monthly
    time_of_day = (req.get('time_of_day') or '09:00').strip()
    timezone = (req.get('timezone') or 'UTC').strip()
    if frequency not in {'daily','weekly','monthly'}:
        return JSONResponse({ 'detail': "frequency must be 'daily','weekly', or 'monthly'" }, status_code=400)
    try:
        hh, mm = [int(x) for x in time_of_day.split(':')]
        assert 0 <= hh <= 23 and 0 <= mm <= 59
    except Exception:
        return JSONResponse({ 'detail': "time_of_day must be 'HH:MM'" }, status_code=400)
    data = verify_session_token(token); email = data.get('email')
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user or not user.is_verified:
            return JSONResponse({ 'detail': 'Email not verified' }, status_code=403)
        from zoneinfo import ZoneInfo
        import datetime as dt
        now_utc = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
        try:
            tz = ZoneInfo(timezone)
        except Exception:
            tz = ZoneInfo('UTC')
        now_local = now_utc.astimezone(tz)
        target_local = now_local.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target_local <= now_local:
            add_days = 1 if frequency=='daily' else (7 if frequency=='weekly' else 30)
            target_local += dt.timedelta(days=add_days)
        next_run = target_local.astimezone(dt.timezone.utc)

        from .audit_engine import canonical_origin
        origin = canonical_origin(url)
        sch = db.query(Schedule).filter(Schedule.user_id == user.id, Schedule.url == origin).first()
        if not sch:
            sch = Schedule(user_id=user.id, url=origin, frequency=frequency, enabled=True, scheduled_hour=hh, scheduled_minute=mm, timezone=timezone, next_run_at=next_run)
            db.add(sch)
        else:
            sch.frequency = frequency; sch.enabled = True; sch.scheduled_hour = hh; sch.scheduled_minute = mm; sch.timezone = timezone; sch.next_run_at = next_run
        db.commit()
        return { 'message': 'Schedule set', 'schedule_id': sch.id, 'next_run_at_utc': sch.next_run_at.isoformat(), 'url': origin, 'frequency': sch.frequency, 'time_of_day': f"{hh:02d}:{mm:02d}", 'timezone': sch.timezone }
    finally:
        db.close()

@app.post('/theme/toggle')
def toggle_theme(request: Request):
    current = request.cookies.get('theme', 'dark')
    new_theme = 'light' if current == 'dark' else 'dark'
    resp = JSONResponse({ 'ok': True, 'theme': new_theme })
    resp.set_cookie('theme', new_theme, max_age=60*60*24*180, samesite='lax')
    return resp

@app.on_event('startup')
def on_startup():
    logger.info('FF Tech AI starting…')
    init_db()
    logger.info('Startup complete ✅')
