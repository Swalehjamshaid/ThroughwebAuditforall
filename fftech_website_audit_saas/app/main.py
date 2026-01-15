import os
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .db import init_db, SessionLocal
from .models import User, Audit
from .auth import router as auth_router
from .audit.analyzer import analyze
from .audit.grader import combine, to_grade
from .audit.report import build_pdf
from .audit.record import export_graph, export_xlsx, export_pptx

app = FastAPI(title=os.getenv('BRAND_NAME','FF Tech') + ' AI Website Audit API')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*']
)

static_dir = os.path.join(os.path.dirname(__file__), 'static')
app.mount('/static', StaticFiles(directory=static_dir), name='static')
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), 'templates'))

app.include_router(auth_router, prefix='/api/auth', tags=['auth'])

# Dependency

def get_db():
    db = SessionLocal();
    try:
        yield db
    finally:
        db.close()

@app.on_event('startup')
def startup():
    init_db()

@app.get('/')
async def index(request: Request):
    return templates.TemplateResponse('index.html', { 'request': request, 'brand': os.getenv('BRAND_NAME','FF Tech') })

@app.post('/api/audit')
async def run_audit(payload: dict, db: Session = Depends(get_db)):
    url = (payload.get('url') or '').strip()
    competitors = payload.get('competitors') or None
    user_email = payload.get('user_email')  # simple demo (replace with JWT/cookie in production)

    if not url.startswith(('http://','https://')):
        raise HTTPException(status_code=400, detail='URL must start with http:// or https://')

    result = await analyze(url, competitors)
    category_scores = result['category_scores']
    overall = combine(category_scores)
    grade = to_grade(overall)

    # 200-word executive summary text synthesized in report builder; here provide structured panels
    strengths = ['Crawlability baseline OK']
    weaknesses = []
    if result['metrics'].get('missing_title',0) or result['metrics'].get('missing_meta_desc',0):
        weaknesses.append('Metadata gaps (titles/descriptions)')
    if result['metrics'].get('http_4xx',0) or result['metrics'].get('http_5xx',0):
        weaknesses.append('HTTP errors present')

    summary = {
        'executive_summary': 'See PDF executive page for ~200-word narrative.',
        'strengths': strengths,
        'weaknesses': weaknesses or ['No critical weaknesses detected in sampled pages'],
        'priority_fixes': ['Resolve 4xx/5xx', 'Add meta descriptions', 'Optimize images and caching']
    }

    # Store only for registered users
    audit_id = None
    report_pdf_path = None
    if user_email:
        user = db.query(User).filter(User.email == user_email).first()
        if user:
            if user.subscription == 'free':
                cnt = db.query(Audit).filter(Audit.user_id == user.id).count()
                if cnt >= 10:
                    raise HTTPException(status_code=402, detail='Free tier limit reached (10 audits). Upgrade to schedule.')
            audit = Audit(user_id=user.id, url=url, overall_score=overall, grade=grade, summary=summary,
                          category_scores=category_scores, metrics=result['metrics'])
            db.add(audit); db.commit(); db.refresh(audit)
            audit_id = audit.id
            report_pdf_path = build_pdf(audit_id, url, overall, grade, category_scores, result['metrics'], out_dir='storage/reports')
            audit.report_pdf_path = report_pdf_path; db.commit()
            # exports
            png = export_graph(audit_id, category_scores, out_dir='storage/exports')
            export_xlsx(audit_id, result['metrics'], category_scores, out_dir='storage/exports')
            export_pptx(audit_id, png, result['metrics'], out_dir='storage/exports')

    return {
        'audit_id': audit_id,
        'url': url,
        'overall_score': overall,
        'grade': grade,
        'summary': summary,
        'category_scores': category_scores,
        'metrics': result['metrics']
    }

@app.get('/api/audits/{audit_id}')
async def get_audit(audit_id: int, db: Session = Depends(get_db)):
    audit = db.query(Audit).filter(Audit.id == audit_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail='Not found')
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
async def get_pdf(audit_id: int, db: Session = Depends(get_db)):
    audit = db.query(Audit).filter(Audit.id == audit_id).first()
    if not audit or not audit.report_pdf_path:
        raise HTTPException(status_code=404, detail='Report not found')
    from fastapi.responses import FileResponse
    return FileResponse(audit.report_pdf_path, media_type='application/pdf', filename=f'audit_{audit_id}.pdf')

@app.post('/api/schedule')
async def schedule(payload: dict, db: Session = Depends(get_db)):
    # simple gate; in production, verify auth via JWT/cookies
    user_email = payload.get('user_email')
    if not user_email:
        raise HTTPException(status_code=401, detail='Sign in required')
    user = db.query(User).filter(User.email == user_email).first()
    if not user:
        raise HTTPException(status_code=401, detail='Invalid user')
    if user.subscription == 'free':
        raise HTTPException(status_code=402, detail='Scheduling is paid feature. Upgrade to enable.')
    # persist schedule (cron expression)
    from .models import Schedule
    s = Schedule(user_id=user.id, url=payload.get('url'), cron=payload.get('cron','0 9 * * 1'), active=True)
    db.add(s); db.commit(); db.refresh(s)
    return {'id': s.id, 'status': 'scheduled'}