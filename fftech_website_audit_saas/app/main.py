import os
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .config import settings
from .db import init_db, SessionLocal
from .models import User, Audit
from .schemas import AuditRequest, AuditResponse, ScheduleRequest
from .audit.analyzer import analyze
from .audit.grader import overall_score, to_grade
from .audit.report import build_pdf
from .audit.record import export_graphs, export_xlsx, export_pptx
from . import auth as auth_router

app = FastAPI(title=f"{settings.BRAND_NAME} AI Website Audit API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOW_ORIGINS.split(',') if settings.ALLOW_ORIGINS else ['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

static_dir = os.path.join(os.path.dirname(__file__), 'static')
app.mount('/static', StaticFiles(directory=static_dir), name='static')
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), 'templates'))

app.include_router(auth_router.router, prefix='/api/auth', tags=['auth'])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event('startup')
async def startup():
    init_db()

@app.get('/')
async def index(request: Request):
    return templates.TemplateResponse('index.html', { 'request': request, 'brand': settings.BRAND_NAME })

@app.post('/api/audit', response_model=AuditResponse)
async def run_audit(payload: AuditRequest, request: Request, db: Session = Depends(get_db)):
    url = payload.url.strip()
    if not (url.startswith('http://') or url.startswith('https://')):
        raise HTTPException(status_code=400, detail='URL must start with http:// or https://')

    result = await analyze(url, payload.competitors)
    primary = result['primary']
    category_scores = primary['category_scores']
    ovr = overall_score(category_scores)
    grade = to_grade(ovr)

    summary = {
        'executive_summary': f"Automated audit for {url}. Focus on reducing errors and improving metadata and performance.",
        'strengths': ['Crawlability baseline OK'],
        'weaknesses': ['Missing titles/meta', 'Performance improvements needed'],
        'priority_fixes': ['Fix 4xx/5xx', 'Add meta descriptions', 'Optimize images']
    }

    # user (very simple demo: pulled from query param or header if present)
    x_email = request.headers.get('x-user-email') or request.query_params.get('email')

    audit_id = None
    if x_email:
        user = db.query(User).filter(User.email == x_email).first()
        if user:
            if user.subscription == 'free':
                count = db.query(Audit).filter(Audit.user_id == user.id).count()
                if count >= 10:
                    raise HTTPException(status_code=402, detail='Free tier limit reached (10 audits). Upgrade to schedule.')
            audit = Audit(
                user_id=user.id,
                url=url,
                overall_score=ovr,
                grade=grade,
                summary=summary,
                category_scores=category_scores,
                metrics=primary['metrics'],
            )
            db.add(audit); db.commit(); db.refresh(audit)
            audit_id = audit.id
            pdf = build_pdf(audit.id, url, ovr, grade, category_scores, primary['metrics'], out_dir='storage/reports')
            audit.report_pdf_path = pdf
            db.commit()
            png = export_graphs(audit.id, category_scores, out_dir='storage/exports')
            export_xlsx(audit.id, primary['metrics'], category_scores, out_dir='storage/exports')
            export_pptx(audit.id, png, primary['metrics'], out_dir='storage/exports')

    return AuditResponse(
        audit_id=audit_id,
        url=url,
        overall_score=ovr,
        grade=grade,
        summary=summary,
        category_scores=category_scores,
        metrics=primary['metrics']
    )

@app.get('/api/audits/{audit_id}', response_model=AuditResponse)
async def get_audit(audit_id: int, db: Session = Depends(get_db)):
    audit = db.query(Audit).filter(Audit.id == audit_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail='Audit not found')
    return AuditResponse(
        audit_id=audit.id,
        url=audit.url,
        overall_score=audit.overall_score,
        grade=audit.grade,
        summary=audit.summary,
        category_scores=audit.category_scores,
        metrics=audit.metrics
    )