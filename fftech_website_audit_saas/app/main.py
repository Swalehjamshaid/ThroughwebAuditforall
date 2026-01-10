
#!/usr/bin/env python3
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .services.config import setup_logging, DEFAULT_OUTPUT_DIR
from .services.report_loader import discover_report_path, load_report_data
from .services.graph_service import generate_graphs
from .services.pdf_service import maybe_generate_pdf, fallback_pdf
from .services.external_imports import import_grader
from .services.db import SessionLocal, engine
from .models import Base, User
from .audit.repository import save_audit, list_user_runs, can_run_audit
from .auth import router as auth_router

logger, _ = setup_logging()

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / 'templates'
STATIC_DIR = BASE_DIR / 'static'
ARTIFACTS_DIR = DEFAULT_OUTPUT_DIR

app = FastAPI(title='FF Tech AI Website Audit SaaS', version='1.0.0')
app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
# expose templates to auth router
app.templates = templates

Base.metadata.create_all(bind=engine)
app.include_router(auth_router)

RUNS: Dict[str, Dict[str, Any]] = {}

# Helpers

def _ensure_dirs():
    for d in [TEMPLATES_DIR, STATIC_DIR, STATIC_DIR / 'img' / 'graphs', ARTIFACTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
_ensure_dirs()

# Routes

@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse('index.html', {'request': request, 'title': 'FF Tech Audit'})

# Open-access audit (no storage)
@app.get('/open-audit', response_class=HTMLResponse)
async def open_audit_page(request: Request):
    return templates.TemplateResponse('open_audit.html', {'request': request, 'title': 'Open Audit'})

@app.post('/open-audit', response_class=HTMLResponse)
async def open_audit_run(request: Request, url: str = Form(...), graph_types: str = Form('auto'), pdf: bool = Form(False)):
    start = time.time()
    grade_all = import_grader(logger)
    result = grade_all(url=url, logger=logger) if callable(grade_all) else {'url': url, 'score': 60, 'grade': 'C', 'metrics': {}}

    # rows for graph generation
    rows: List[Dict[str, Any]] = []
    rows.append({'url': url, 'score': result['score'], 'grade': result['grade']})

    run_id = str(uuid.uuid4())
    graphs = generate_graphs(rows, STATIC_DIR, graph_types.split(','), logger, run_id)

    pdf_path = None
    if pdf:
        pdf_path = maybe_generate_pdf(rows, ARTIFACTS_DIR, logger) or fallback_pdf(rows, graphs, ARTIFACTS_DIR, logger)

    RUNS[run_id] = {
        'url': url,
        'score': result['score'],
        'grade': result['grade'],
        'graphs': [str(p) for p in graphs],
        'pdf_path': str(pdf_path) if pdf_path else None,
        'duration': round(time.time() - start, 2),
        'mode': 'open'
    }
    return RedirectResponse(url=f'/report/{run_id}', status_code=303)

# Registered user dashboard
@app.get('/dashboard', response_class=HTMLResponse)
async def dashboard(request: Request):
    email = request.cookies.get('user_email')
    if not email:
        return RedirectResponse(url='/login', status_code=303)
    with SessionLocal() as session:
        user = session.query(User).filter(User.email == email).one_or_none()
        runs = list_user_runs(session, user) if user else []
    return templates.TemplateResponse('dashboard.html', {'request': request, 'title': 'Dashboard', 'email': email, 'runs': runs})

@app.post('/run-audit', response_class=HTMLResponse)
async def run_audit(request: Request, url: str = Form(...), graph_types: str = Form('auto'), pdf: bool = Form(False)):
    email = request.cookies.get('user_email')
    if not email:
        return RedirectResponse(url='/login', status_code=303)
    with SessionLocal() as session:
        user = session.query(User).filter(User.email == email).one_or_none()
        if not user:
            return RedirectResponse(url='/login', status_code=303)
        if not can_run_audit(session, user):
            return templates.TemplateResponse('dashboard.html', {'request': request, 'title': 'Dashboard', 'email': email, 'runs': [], 'message': 'Free plan limit reached (10 audits).'})
        start = time.time()
        grade_all = import_grader(logger)
        result = grade_all(url=url, logger=logger) if callable(grade_all) else {'url': url, 'score': 60, 'grade': 'C', 'metrics': {}}
        rows = [{'url': url, 'score': result['score'], 'grade': result['grade']}] 
        run_id = str(uuid.uuid4())
        graphs = generate_graphs(rows, STATIC_DIR, graph_types.split(','), logger, run_id)
        pdf_path = None
        if pdf:
            pdf_path = maybe_generate_pdf(rows, ARTIFACTS_DIR, logger) or fallback_pdf(rows, graphs, ARTIFACTS_DIR, logger)
        saved = save_audit(session, user, url, result, [str(p) for p in graphs], str(pdf_path) if pdf_path else None)
        return RedirectResponse(url=f'/report/{saved.id}', status_code=303)

@app.get('/report/{run_id}', response_class=HTMLResponse)
async def report_page(request: Request, run_id: str):
    # try DB run first
    with SessionLocal() as session:
        try:
            rid = int(run_id)
            run = session.get(__import__('app.models', fromlist=['AuditRun']).AuditRun, rid)
            if run:
                graphs = json.loads(run.graphs_json)
                data = {
                    'url': run.url,
                    'score': run.score,
                    'grade': run.grade,
                    'graphs': graphs,
                    'pdf_path': run.pdf_path,
                    'duration': None,
                    'mode': 'registered'
                }
                return templates.TemplateResponse('report.html', {'request': request, 'title': 'Audit Report Output', 'data': data})
        except Exception:
            pass
    # fallback to memory runs
    data = RUNS.get(run_id)
    if not data:
        return templates.TemplateResponse('base_open.html', {'request': request, 'title': 'Not Found', 'content': f'Run {run_id} not found.'})
    return templates.TemplateResponse('report.html', {'request': request, 'title': 'Audit Report Output', 'data': data})

@app.get('/health')
async def health():
    return {'status': 'ok'}

