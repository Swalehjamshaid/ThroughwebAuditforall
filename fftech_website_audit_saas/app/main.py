import os, uuid
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from .db import init_db, SessionLocal
from .models import User, Audit
from .auth import router as auth_router
from .audit.analyzer import analyze
from .audit.grader import overall_score, to_grade
from .audit.report import build_pdf
from .audit.record import export_graphs, export_xlsx, export_pptx

BRAND = os.getenv('BRAND_NAME', 'FF Tech')
REPORT_DIR = 'storage/reports'
EXPORT_DIR = 'storage/exports'

app = FastAPI(title=f"{BRAND} – Audit API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

app.mount('/static', StaticFiles(directory=os.path.join(os.path.dirname(__file__), 'static')), name='static')
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), 'templates'))

app.include_router(auth_router, prefix='/api/auth', tags=['auth'])

@app.on_event('startup')
async def startup():
    init_db()

@app.get('/')
async def index(request: Request):
    return templates.TemplateResponse('index.html', { 'request': request, 'brand': BRAND })

# Helper to get DB session
class _DB:
    def __enter__(self):
        self.db = SessionLocal(); return self.db
    def __exit__(self, exc_type, exc, tb):
        self.db.close()

@app.post('/api/audit')
async def run_audit(payload: dict, request: Request):
    url = (payload or {}).get('url','').strip()
    competitors = (payload or {}).get('competitors', [])
    if not url.startswith('http://') and not url.startswith('https://'):
        raise HTTPException(status_code=400, detail='URL must start with http:// or https://')

    result = await analyze(url, competitors)
    cat = result['category_scores']
    ovr = overall_score(cat)
    grade = to_grade(ovr)

    summary = {
        'executive_summary': f"Automated audit for {url}. Focus on reducing HTTP errors and improving metadata/performance.",
        'strengths': ['Crawlability baseline OK'],
        'weaknesses': ['Missing titles/descriptions', 'Performance improvements needed'],
        'priority_fixes': ['Fix 4xx/5xx', 'Add meta descriptions', 'Optimize images']
    }

    # Always build a PDF and give a download URL (open users get temp id)
    temp_id = str(uuid.uuid4())
    pdf_path = build_pdf(temp_id, url, ovr, grade, cat, result['metrics'], out_dir=REPORT_DIR)
    png = export_graphs(temp_id, cat, out_dir=EXPORT_DIR)
    export_xlsx(temp_id, result['metrics'], cat, out_dir=EXPORT_DIR)
    export_pptx(temp_id, png, result['metrics'], out_dir=EXPORT_DIR)

    # Optional store for registered users if header provided
    email = request.headers.get('x-user-email')
    audit_id = None
    if email:
        with _DB() as db:
            user = db.query(User).filter(User.email==email).first()
            if user:
                if user.subscription=='free':
                    count = db.query(Audit).filter(Audit.user_id==user.id).count()
                    if count >= 10:
                        # keep temp download but no store
                        stored = False
                    else:
                        a = Audit(user_id=user.id, url=url, overall_score=ovr, grade=grade,
                                  summary=summary, category_scores=cat, metrics=result['metrics'],
                                  report_pdf_path=pdf_path)
                        db.add(a); db.commit(); db.refresh(a)
                        audit_id = a.id

    download_url = f"/api/reports/pdf/temp/{temp_id}"
    if audit_id:
        download_url = f"/api/reports/pdf/{audit_id}"

    return JSONResponse({
        'audit_id': audit_id,
        'url': url,
        'overall_score': ovr,
        'grade': grade,
        'summary': summary,
        'category_scores': cat,
        'metrics': result['metrics'],
        'download_url': download_url
    })

@app.get('/api/reports/pdf/{audit_id}')
async def download_pdf(audit_id: int):
    with _DB() as db:
        a = db.query(Audit).filter(Audit.id==audit_id).first()
        if not a or not a.report_pdf_path:
            raise HTTPException(status_code=404, detail='report not found')
        return FileResponse(a.report_pdf_path, media_type='application/pdf', filename=f'audit_{audit_id}.pdf')

@app.get('/api/reports/pdf/temp/{doc_id}')
async def download_temp(doc_id: str):
    path = os.path.join(REPORT_DIR, f'audit_{doc_id}.pdf')
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail='temp report expired')
    return FileResponse(path, media_type='application/pdf', filename=f'audit_{doc_id}.pdf')