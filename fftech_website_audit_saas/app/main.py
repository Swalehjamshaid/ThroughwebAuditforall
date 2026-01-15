
import os, bcrypt
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .config import settings
from .db import init_db, SessionLocal
from . import models
from .auth import router as auth_router, read_session
from .audit.analyzer import analyze
from .audit.grader import overall_score, to_grade
from .audit.report import build_pdf
from .audit.record import export_graphs, export_pptx, export_xlsx

app = FastAPI(title=f"{settings.BRAND_NAME} AI Website Audit API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

static_dir = os.path.join(os.path.dirname(__file__), 'static')
app.mount('/static', StaticFiles(directory=static_dir), name='static')
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), 'templates'))

# DB dep

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Seed admin on startup
@app.on_event('startup')
def startup():
    init_db()
    db = SessionLocal()
    try:
        admin = db.query(models.User).filter(models.User.email==settings.ADMIN_EMAIL).first()
        if not admin:
            pw_hash = bcrypt.hashpw(settings.ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
            admin = models.User(email=settings.ADMIN_EMAIL, is_verified=True, role='admin', password_hash=pw_hash, subscription='pro')
            db.add(admin); db.commit()
        else:
            if not admin.password_hash:
                admin.password_hash = bcrypt.hashpw(settings.ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
                admin.role = 'admin'; admin.is_verified = True
                db.commit()
    finally:
        db.close()

# Routers
app.include_router(auth_router, prefix='/api/auth', tags=['auth'])

# Index UI
@app.get('/')
async def index(request: Request):
    return templates.TemplateResponse('index.html', { 'request': request, 'brand': settings.BRAND_NAME })

# Admin UI
@app.get('/admin')
async def admin_page(request: Request):
    sess = read_session(request)
    if not sess or sess.get('role') != 'admin':
        raise HTTPException(status_code=401, detail='admin required')
    return templates.TemplateResponse('admin.html', { 'request': request, 'brand': settings.BRAND_NAME, 'email': sess['email'] })

# API: Run audit (open or registered)
@app.post('/api/audit')
async def run_audit(payload: dict, request: Request, db: Session = Depends(get_db)):
    url = payload.get('url','').strip()
    if not (url.startswith('http://') or url.startswith('https://')):
        raise HTTPException(status_code=400, detail='URL must start with http:// or https://')
    result = await analyze(url, payload.get('competitors'))
    ovr = overall_score(result['category_scores'])
    grade = to_grade(ovr)
    summary = {
        'executive_summary': f"Automated audit for {url}. Focus on reducing errors and improving on-page metadata and performance.",
        'strengths': ['Crawlability baseline OK'],
        'weaknesses': ['Missing titles/descriptions', 'Performance improvements needed'],
        'priority_fixes': ['Fix 4xx/5xx', 'Add meta descriptions', 'Optimize images']
    }

    sess = read_session(request)
    audit_id = None
    if sess:
        # store for registered user with free tier limit
        user = db.query(models.User).filter(models.User.email==sess['email']).first()
        if user:
            if user.subscription == 'free':
                count = db.query(models.Audit).filter(models.Audit.user_id==user.id).count()
                if count >= 10:
                    raise HTTPException(status_code=402, detail='Free tier limit reached (10 audits). Upgrade to schedule.')
            audit = models.Audit(user_id=user.id, url=url, overall_score=ovr, grade=grade, summary=summary, category_scores=result['category_scores'], metrics=result['metrics'])
            db.add(audit); db.commit(); db.refresh(audit)
            audit_id = audit.id
            pdf = build_pdf(audit.id, url, ovr, grade, result['category_scores'], result['metrics'], out_dir='storage/reports')
            audit.report_pdf_path = pdf; db.commit()
            png = export_graphs(audit.id, result['category_scores'], out_dir='storage/exports')
            export_xlsx(audit.id, result['metrics'], result['category_scores'], out_dir='storage/exports')
            export_pptx(audit.id, png, result['metrics'], out_dir='storage/exports')

    return {
        'audit_id': audit_id,
        'url': url,
        'overall_score': ovr,
        'grade': grade,
        'summary': summary,
        'category_scores': result['category_scores'],
        'metrics': result['metrics']
    }

@app.get('/api/audits/{audit_id}')
async def get_audit(audit_id: int, request: Request, db: Session = Depends(get_db)):
    sess = read_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail='sign in required')
    audit = db.query(models.Audit).filter(models.Audit.id==audit_id).first()
    if not audit: raise HTTPException(status_code=404, detail='Audit not found')
    return {
        'audit_id': audit.id,
        'url': audit.url,
        'overall_score': audit.overall_score,
        'grade': audit.grade,
        'summary': audit.summary,
        'category_scores': audit.category_scores,
        'metrics': audit.metrics
    }

@app.get('/api/reports/pdf/{audit_id}')
async def download_pdf(audit_id: int, request: Request, db: Session = Depends(get_db)):
    sess = read_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail='sign in required')
    audit = db.query(models.Audit).filter(models.Audit.id==audit_id).first()
    if not audit or not audit.report_pdf_path:
        raise HTTPException(status_code=404, detail='Report not found')
    return FileResponse(audit.report_pdf_path, media_type='application/pdf', filename=f'audit_{audit_id}.pdf')

@app.post('/api/schedule')
async def schedule(payload: dict, request: Request, db: Session = Depends(get_db)):
    sess = read_session(request)
    if not sess: raise HTTPException(status_code=401, detail='sign in required')
    user = db.query(models.User).filter(models.User.email==sess['email']).first()
    if user.subscription == 'free':
        raise HTTPException(status_code=402, detail='Scheduling is paid feature. Upgrade to enable.')
    s = models.Schedule(user_id=user.id, url=payload.get('url'), cron=payload.get('cron','0 3 * * *'), active=True)
    db.add(s); db.commit(); db.refresh(s)
    return {'id': s.id, 'status': 'scheduled'}

# Admin APIs
@app.get('/api/admin/stats')
async def admin_stats(request: Request, db: Session = Depends(get_db)):
    sess = read_session(request)
    if not sess or sess.get('role') != 'admin':
        raise HTTPException(status_code=401, detail='admin required')
    users = db.query(models.User).count()
    audits = db.query(models.Audit).count()
    return {'users': users, 'audits': audits}
