
import os
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db, SessionLocal
from .models import User, Audit
from .auth import router as auth_router
from .audit.analyzer import analyze
from .audit.grader import overall_score, to_grade
from .audit.report import build_pdf
from .audit.record import export_graphs, export_xlsx, export_pptx

app = FastAPI(title='FF Tech AI Website Audit')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_headers=['*'], allow_methods=['*'], allow_credentials=True)

static_dir = os.path.join(os.path.dirname(__file__), 'static')
app.mount('/static', StaticFiles(directory=static_dir), name='static')
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), 'templates'))

@app.on_event('startup')
def startup():
    init_db()

# ---------- Web UI Routes ----------
@app.get('/')
async def page_index(request: Request):
    return templates.TemplateResponse('index.html', {"request": request})

@app.get('/login')
async def page_login(request: Request):
    return templates.TemplateResponse('login.html', {"request": request})

@app.get('/register')
async def page_register(request: Request):
    return templates.TemplateResponse('register.html', {"request": request})

@app.get('/verify')
async def page_verify(request: Request, token: str = ''):
    return templates.TemplateResponse('verify.html', {"request": request, "token": token})

@app.get('/dashboard')
async def page_dashboard(request: Request):
    return templates.TemplateResponse('dashboard.html', {"request": request})

@app.get('/admin')
async def page_admin(request: Request):
    return templates.TemplateResponse('admin.html', {"request": request})

@app.get('/new-audit')
async def page_new_audit(request: Request):
    return templates.TemplateResponse('new_audit.html', {"request": request})

@app.get('/audit/{audit_id}')
async def page_audit_detail(request: Request, audit_id: int):
    return templates.TemplateResponse('audit_detail.html', {"request": request, "audit_id": audit_id})

# ---------- API ----------
app.include_router(auth_router, prefix='/api/auth', tags=['auth'])

@app.post('/api/audit')
async def api_audit(payload: dict):
    url = (payload.get('url') or '').strip()
    if not url.startswith(('http://','https://')):
        raise HTTPException(status_code=400, detail='URL must start with http(s)://')

    res = await analyze(url, payload.get('competitors'))
    cat = res['category_scores']
    ovr = overall_score(cat)
    grade = to_grade(ovr)

    summary = {
        'executive_summary': f'Automated audit for {url}. Focus on crawl errors, on-page metadata, and performance.',
        'strengths': ['Crawlability baseline OK'],
        'weaknesses': ['Missing titles/descriptions', 'Performance improvements needed'],
        'priority_fixes': ['Fix 4xx/5xx', 'Add meta descriptions', 'Optimize images']
    }

    # Anonymous by default → no storage; if payload carries email and exists → store
    db = SessionLocal()
    user_email = payload.get('email')
    audit_id = None
    try:
        if user_email:
            user = db.query(User).filter(User.email==user_email).first()
            if user:
                if user.subscription=='free':
                    count = db.query(Audit).filter(Audit.user_id==user.id).count()
                    if count >= 10:
                        raise HTTPException(status_code=402, detail='Free tier limit reached (10 audits)')
                audit = Audit(user_id=user.id, url=url, overall_score=ovr, grade=grade,
                               summary=summary, category_scores=cat, metrics=res['metrics'])
                db.add(audit); db.commit(); db.refresh(audit)
                audit_id = audit.id
                pdf = build_pdf(audit.id, url, ovr, grade, cat, res['metrics'], out_dir='storage/reports')
                audit.report_pdf_path = pdf; db.commit()
                # exports
                png = export_graphs(audit.id, cat, out_dir='storage/exports')
                export_xlsx(audit.id, res['metrics'], cat, out_dir='storage/exports')
                export_pptx(audit.id, png, res['metrics'], out_dir='storage/exports')
    finally:
        db.close()

    return {
        'audit_id': audit_id,
        'url': url,
        'overall_score': ovr,
        'grade': grade,
        'summary': summary,
        'category_scores': cat,
        'metrics': res['metrics']
    }

@app.get('/api/reports/pdf/{audit_id}')
async def api_pdf(audit_id: int):
    from fastapi.responses import FileResponse
    db = SessionLocal()
    try:
        a = db.query(Audit).filter(Audit.id==audit_id).first()
        if not a or not a.report_pdf_path:
            raise HTTPException(status_code=404, detail='Report not found')
        return FileResponse(a.report_pdf_path, media_type='application/pdf', filename=f'audit_{audit_id}.pdf')
    finally:
        db.close()
