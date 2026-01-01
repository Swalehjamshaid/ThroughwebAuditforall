from fastapi import FastAPI, Response, Request, Depends, HTTPException, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import secrets
import os
import asyncio
import logging

from .settings import settings
from .db import init_db, db_ok, SessionLocal
from .models import User, VerificationToken, Website, Audit, Schedule
from .security import hash_password, verify_password, create_jwt, decode_jwt
from .emailer import send_email, smtp_configured
from .report import generate_report
from .audit_stub import run_stub_audit, compute_grade
from .scheduler import schedule_loop

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="FF Tech – WebAudit v4.5")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')
jinja_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape(['html']))

@app.on_event("startup")
def startup() -> None:
    init_db()
    logging.info('DB initialized; starting scheduler task')
    asyncio.create_task(schedule_loop())

@app.get('/health')
def health() -> dict:
    return {"status": "ok", "env": settings.ENV}

@app.get('/db/health')
def db_health() -> dict:
    return {"database_ok": db_ok()}

# DB dependency
def get_db():
    with SessionLocal() as db:
        yield db

# Helpers
def absolute_url(request: Request, path: str) -> str:
    scheme = request.headers.get('x-forwarded-proto') or request.url.scheme
    host = request.headers.get('x-forwarded-host') or request.url.netloc
    return f"{scheme}://{host}{path}"

def ui_current_user(request: Request, db: Session) -> User | None:
    token = request.cookies.get('auth')
    if not token:
        return None
    data = decode_jwt(token)
    if not data:
        return None
    return db.query(User).filter(User.id == data.get('sub')).first()

# Pages
@app.get('/', response_class=HTMLResponse)
async def landing(request: Request, db: Session = Depends(get_db)):
    user = ui_current_user(request, db)
    tpl = jinja_env.get_template('landing.html')
    return tpl.render(user=user)

# === NEW: Guest Audit Endpoint ===
@app.post('/ui/audit_guest', response_class=RedirectResponse)
async def audit_guest(request: Request, url: str = Form(...), db: Session = Depends(get_db)):
    """
    Allows non-logged-in users to audit any website directly from the homepage.
    Creates a temporary Website entry (user_id=None), runs audit, saves results.
    """
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    try:
        # Create temporary website entry (no user associated)
        website = Website(user_id=None, url=url)
        db.add(website)
        db.commit()
        db.refresh(website)

        # Run stub audit
        metrics = run_stub_audit(website.url)
        numeric = [v for v in metrics.values() if isinstance(v, (int, float))]
        overall = sum(numeric) / len(numeric) if numeric else 0
        grade = compute_grade(overall)

        # Save audit
        audit = Audit(
            website_id=website.id,
            metrics=metrics,
            grade=grade,
            metrics_count=1100
        )
        db.add(audit)
        db.commit()
        db.refresh(audit)

        # Redirect to results page
        return RedirectResponse(
            url=f"/results?website_id={website.id}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    except Exception as e:
        logging.error(f"Guest audit failed for URL {url}: {str(e)}")
        # Redirect back to home with flash message (optional enhancement later)
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

# Existing routes below (unchanged)
@app.get('/register', response_class=HTMLResponse)
async def register_page(request: Request):
    tpl = jinja_env.get_template('register.html')
    return tpl.render()

@app.post('/ui/register', response_class=HTMLResponse)
async def register_submit(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    u = User(email=email, password_hash=hash_password(password))
    u.verified = (not smtp_configured()) and settings.AUTO_VERIFY
    db.add(u); db.commit(); db.refresh(u)
    if smtp_configured():
        tok = secrets.token_urlsafe(32)
        vt = VerificationToken(user_id=u.id, token=tok, expires_at=datetime.now(timezone.utc)+timedelta(days=2))
        db.add(vt); db.commit()
        verify_link = absolute_url(request, f"/auth/verify?token={tok}")
        send_email(u.email, "Verify your FF Tech account", f"<p>Click to verify: <a href='{verify_link}'>Verify</a></p>")
    tpl = jinja_env.get_template('register_done.html')
    return tpl.render(email=email, auto_verified=u.verified)

@app.get('/auth/verify', response_class=HTMLResponse)
async def verify(token: str, request: Request, db: Session = Depends(get_db)):
    vt = db.query(VerificationToken).filter(VerificationToken.token == token).first()
    if not vt or vt.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    u = db.query(User).get(vt.user_id); u.verified = True
    db.add(u); db.commit()
    return RedirectResponse(url='/verify_success', status_code=status.HTTP_303_SEE_OTHER)

@app.get('/verify_success', response_class=HTMLResponse)
async def verify_success():
    tpl = jinja_env.get_template('verify_success.html')
    return tpl.render()

@app.get('/login', response_class=HTMLResponse)
async def login_page():
    tpl = jinja_env.get_template('login.html')
    return tpl.render()

@app.post('/ui/login')
async def ui_login(response: Response, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == email).first()
    if not u or not verify_password(password, u.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_jwt({"sub": u.id, "role": u.role}, 120)
    resp = RedirectResponse(url='/', status_code=status.HTTP_303_SEE_OTHER)
    resp.set_cookie('auth', token, httponly=True, secure=True, samesite='lax', max_age=60*120)
    return resp

@app.get('/logout')
async def ui_logout(response: Response):
    resp = RedirectResponse(url='/', status_code=status.HTTP_303_SEE_OTHER)
    resp.delete_cookie('auth')
    return resp

# UI: Add Website (logged-in users)
@app.post('/ui/add-website', response_class=HTMLResponse)
async def add_website(request: Request, url: str = Form(...), db: Session = Depends(get_db)):
    user = ui_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    w = Website(user_id=user.id, url=url)
    db.add(w); db.commit(); db.refresh(w)
    return RedirectResponse(url=f"/results?website_id={w.id}", status_code=status.HTTP_303_SEE_OTHER)

# Results page (works for both guest and logged-in audits)
@app.get('/results', response_class=HTMLResponse)
async def results_page(request: Request, website_id: int, db: Session = Depends(get_db)):
    user = ui_current_user(request, db)
    w = db.query(Website).get(website_id)
    if not w:
        raise HTTPException(status_code=404, detail="Website not found")
    last = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    tpl = jinja_env.get_template('results.html')
    return tpl.render(user=user, website=w, audit=last)

# UI: Run Audit Now (logged-in only)
@app.post('/ui/audits/run')
async def ui_run_audit(request: Request, website_id: int = Form(...), db: Session = Depends(get_db)):
    user = ui_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    w = db.query(Website).get(website_id)
    if not w:
        raise HTTPException(status_code=404, detail="Website not found")
    metrics = run_stub_audit(w.url)
    numeric = [v for v in metrics.values() if isinstance(v, (int, float))]
    overall = (sum(numeric) / max(len(numeric), 1))
    grade = compute_grade(overall)
    a = Audit(website_id=w.id, metrics=metrics, grade=grade, metrics_count=1100)
    db.add(a); db.commit(); db.refresh(a)
    return RedirectResponse(url=f"/results?website_id={w.id}", status_code=status.HTTP_303_SEE_OTHER)

# Audit history
@app.get('/audit_history', response_class=HTMLResponse)
async def audit_history(request: Request, website_id: int, db: Session = Depends(get_db)):
    user = ui_current_user(request, db)
    w = db.query(Website).get(website_id)
    rows = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).all()
    tpl = jinja_env.get_template('audit_history.html')
    return tpl.render(user=user, website=w, audits=rows)

# Schedule pages
@app.get('/schedule', response_class=HTMLResponse)
async def schedule_page(request: Request, website_id: int, db: Session = Depends(get_db)):
    user = ui_current_user(request, db)
    w = db.query(Website).get(website_id)
    tpl = jinja_env.get_template('schedule.html')
    return tpl.render(user=user, website=w, saved=False)

@app.post('/ui/schedule', response_class=HTMLResponse)
async def schedule_submit(request: Request, website_id: int = Form(...), timezone_name: str = Form(...), hour: int = Form(...), minute: int = Form(...), db: Session = Depends(get_db)):
    user = ui_current_user(request, db)
    w = db.query(Website).get(website_id)
    if not w:
        raise HTTPException(status_code=404, detail="Website not found")
    s = Schedule(user_id=w.user_id, website_id=w.id, timezone=timezone_name, hour=hour, minute=minute, enabled=True)
    db.add(s); db.commit(); db.refresh(s)
    tpl = jinja_env.get_template('schedule.html')
    return tpl.render(user=user, website=w, saved=True, schedule=s)

# Admin dashboard
@app.get('/admin/dashboard', response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    u = ui_current_user(request, db)
    if not u or u.role != 'admin':
        raise HTTPException(status_code=403, detail='Admin only')
    users = db.query(User).order_by(User.created_at.desc()).all()
    websites = db.query(Website).order_by(Website.created_at.desc()).all()
    tpl = jinja_env.get_template('admin_dashboard.html')
    return tpl.render(user=u, users=users, websites=websites)

# Minimal APIs (kept unchanged)
@app.post('/websites')
def add_site(payload: dict, db: Session = Depends(get_db)):
    email = payload.get('email')
    u = db.query(User).filter(User.email == email).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    url = payload.get('url')
    w = Website(user_id=u.id, url=url)
    db.add(w); db.commit(); db.refresh(w)
    return {"website_id": w.id, "url": w.url}

@app.post('/audits/run')
def run_audit(payload: dict, db: Session = Depends(get_db)):
    website_id = payload.get('website_id')
    w = db.query(Website).get(website_id)
    if not w:
        raise HTTPException(status_code=404, detail="Website not found")
    metrics = run_stub_audit(w.url)
    numeric = [v for v in metrics.values() if isinstance(v, (int, float))]
    overall = (sum(numeric) / max(len(numeric), 1))
    grade = compute_grade(overall)
    a = Audit(website_id=w.id, metrics=metrics, grade=grade, metrics_count=1100)
    db.add(a); db.commit(); db.refresh(a)
    return {"audit_id": a.id, "grade": grade, "metrics_count": a.metrics_count}

@app.get('/reports/daily')
def daily_report(website_id: int, db: Session = Depends(get_db)):
    w = db.query(Website).get(website_id)
    if not w:
        raise HTTPException(status_code=404, detail="Website not found")
    metrics = {"overall": 90, "lcp": 2100, "inp": 160, "cls": 0.03}
    pdf = generate_report(w.url, "A", "Daily snapshot summarizing top issues and improvements.", metrics, accumulated=False)
    return Response(content=pdf, media_type="application/pdf")

@app.get('/reports/accumulated')
def accumulated_report(website_id: int, db: Session = Depends(get_db)):
    w = db.query(Website).get(website_id)
    if not w:
        raise HTTPException(status_code=404, detail="Website not found")
    metrics = {"overall": 92, "lcp": 1900, "inp": 140, "cls": 0.02}
    pdf = generate_report(w.url, "A", "Accumulated trend analysis showing improvement over time.", metrics, accumulated=True)
    return Response(content=pdf, media_type="application/pdf")
