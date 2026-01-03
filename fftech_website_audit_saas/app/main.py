
import os
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from .db import Base, engine, SessionLocal
from .models import User, Website, Audit, Subscription
from .auth import hash_password, verify_password, create_token, decode_token
from .email_utils import send_verification_email
from .audit.engine import run_basic_checks
from .audit.grader import compute_overall, grade_from_score, summarize_200_words
from .audit.report import render_pdf
from datetime import datetime

UI_BRAND_NAME = os.getenv('UI_BRAND_NAME','FF Tech')

app = FastAPI()
app.mount('/static', StaticFiles(directory='app/static'), name='static')
templates = Jinja2Templates(directory='app/templates')

Base.metadata.create_all(bind=engine)

# Dependency

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Simple session management (placeholder)
current_user = None

@app.get('/')
async def index(request: Request):
    return templates.TemplateResponse('index.html', { 'request': request, 'UI_BRAND_NAME': UI_BRAND_NAME, 'user': current_user })

@app.get('/register')
async def register_get(request: Request):
    return templates.TemplateResponse('register.html', {'request': request, 'UI_BRAND_NAME': UI_BRAND_NAME, 'user': current_user})

@app.post('/register')
async def register_post(request: Request, email: str = Form(...), password: str = Form(...), confirm_password: str = Form(...), db: Session = Depends(get_db)):
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
    return templates.TemplateResponse('verify.html', {'request': request, 'success': success, 'UI_BRAND_NAME': UI_BRAND_NAME, 'user': current_user})

@app.get('/login')
async def login_get(request: Request):
    return templates.TemplateResponse('login.html', {'request': request, 'UI_BRAND_NAME': UI_BRAND_NAME, 'user': current_user})

@app.post('/login')
async def login_post(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    global current_user
    u = db.query(User).filter(User.email == email).first()
    if not u or not verify_password(password, u.password_hash) or not u.verified:
        return RedirectResponse('/login', status_code=303)
    current_user = u
    return RedirectResponse('/dashboard', status_code=303)

@app.get('/logout')
async def logout(request: Request):
    global current_user
    current_user = None
    return RedirectResponse('/', status_code=303)

@app.get('/dashboard')
async def dashboard(request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user:
        return RedirectResponse('/login', status_code=303)
    websites = db.query(Website).filter(Website.user_id == current_user.id).all()
    # Simple trend
    trend = {'labels': ["W1","W2","W3","W4","W5"], 'values': [80, 82, 78, 85, 88]}
    summary = {'grade': 'A', 'health_score': 88}
    schedule = {'daily_time': '09:00', 'timezone': 'UTC', 'enabled': True}
    return templates.TemplateResponse('dashboard.html', {'request': request, 'UI_BRAND_NAME': UI_BRAND_NAME, 'user': current_user, 'websites': websites, 'trend': trend, 'summary': summary, 'schedule': schedule})

@app.get('/audit/new')
async def new_audit_get(request: Request):
    global current_user
    if not current_user:
        return RedirectResponse('/login', status_code=303)
    return templates.TemplateResponse('new_audit.html', {'request': request, 'UI_BRAND_NAME': UI_BRAND_NAME, 'user': current_user})

@app.post('/audit/new')
async def new_audit_post(request: Request, url: str = Form(...), enable_schedule: str = Form(None), db: Session = Depends(get_db)):
    global current_user
    if not current_user:
        return RedirectResponse('/login', status_code=303)
    # Subscription limit
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    if not sub:
        sub = Subscription(user_id=current_user.id, plan='free', active=True, audits_used=0)
        db.add(sub); db.commit(); db.refresh(sub)
    if sub.plan == 'free' and sub.audits_used >= 10:
        return RedirectResponse('/dashboard', status_code=303)
    w = Website(user_id=current_user.id, url=url)
    db.add(w); db.commit(); db.refresh(w)
    return RedirectResponse(f'/audit/run/{w.id}', status_code=303)

@app.get('/audit/run/{website_id}')
async def run_audit(website_id: int, request: Request, db: Session = Depends(get_db)):
    global current_user
    if not current_user:
        return RedirectResponse('/login', status_code=303)
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    if not w:
        return RedirectResponse('/dashboard', status_code=303)
    res = run_basic_checks(w.url)
    category_scores = res['category_scores']
    overall = compute_overall(category_scores)
    grade = grade_from_score(overall)
    exec_summary = summarize_200_words(w.url, category_scores, res['top_issues'])
    audit = Audit(user_id=current_user.id, website_id=w.id, health_score=int(overall), grade=grade, exec_summary=exec_summary,
                  category_scores_json=str([{'name':k,'score':int(v)} for k,v in category_scores.items()]),
                  metrics_json=str(res['metrics']))
    db.add(audit); db.commit(); db.refresh(audit)
    w.last_audit_at = audit.created_at; w.last_grade = grade; db.commit()
    # increment subscription usage
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    if sub: sub.audits_used += 1; db.commit()
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
