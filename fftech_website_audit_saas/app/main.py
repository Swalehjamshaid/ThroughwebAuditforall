
#!/usr/bin/env python3
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, Form, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .services.config import setup_logging, DEFAULT_OUTPUT_DIR
from .services.report_loader import discover_report_path, load_report_data
from .services.graph_service import generate_graphs
from .services.pdf_service import maybe_generate_pdf, fallback_pdf
from .services.external_imports import import_grader
from .services.audit_engine import run_audit
from .services.scoring import compute_category_scores, compute_overall_score
from .services.auth_service import create_login_token, verify_login_token, build_magic_link

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / 'templates'
STATIC_DIR = BASE_DIR / 'static'
ARTIFACTS_DIR = DEFAULT_OUTPUT_DIR

logger, _ = setup_logging()

app = FastAPI(title='FF Tech AI Website Audit SaaS', version='1.0.0')
app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

RUNS: Dict[str, Dict[str, Any]] = {}

# Home -> open access & login links
@app.get('/', response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse('index.html', {'request': request, 'title': 'FF Tech Audit'})

# Open access page
@app.get('/open', response_class=HTMLResponse)
async def open_access(request: Request):
    return templates.TemplateResponse('open_access.html', {'request': request, 'title': 'Open Access Audit'})

# Open access audit (no storage)
@app.post('/audit/open', response_class=HTMLResponse)
async def audit_open(request: Request, url: str = Form(...), graph_types: str = Form('auto')):
    metrics = await run_audit(url)
    cats = compute_category_scores(metrics)
    overall_score, grade = compute_overall_score(cats)
    graphs = generate_graphs([metrics], STATIC_DIR, graph_types.split(','), logger)
    pdf_path = fallback_pdf([metrics], graphs, ARTIFACTS_DIR, logger)
    return templates.TemplateResponse('audit_detail.html', {
        'request': request,
        'url': url,
        'category_scores': cats,
        'overall_score': round(overall_score, 2),
        'grade': grade,
        'graphs': [str(p) for p in graphs],
        'pdf_path': str(pdf_path) if pdf_path else None,
        'title': 'Open Audit Result'
    })

# Login
@app.get('/login', response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse('login.html', {'request': request, 'title': 'Login/Register'})

@app.post('/login')
async def login_send_link(email: str = Form(...)):
    token = create_login_token(email)
    link = build_magic_link(token)
    logger.info('Magic login link for %s: %s', email, link)
    # TODO: Send email via provider
    return RedirectResponse(url=f'/verify?token={token}', status_code=303)

@app.get('/verify', response_class=HTMLResponse)
async def verify(request: Request, token: str):
    email = verify_login_token(token)
    if not email:
        return templates.TemplateResponse('verify.html', {'request': request, 'message': 'Invalid or expired link', 'title':'Verification'})
    response = templates.TemplateResponse('verify.html', {'request': request, 'message': 'Login successful', 'title':'Verification'})
    response.set_cookie('session_email', email, httponly=True, max_age=7*24*3600)
    return response

# Dashboard (registered)
@app.get('/dashboard', response_class=HTMLResponse)
async def dashboard(request: Request, session_email: Optional[str] = Cookie(None)):
    if not session_email:
        return RedirectResponse('/login', status_code=303)
    return templates.TemplateResponse('dashboard.html', {'request': request, 'email': session_email, 'title': 'Dashboard'})

# Registered audit (stores history in memory; swap to DB in production)
@app.post('/audit', response_class=HTMLResponse)
async def audit_registered(request: Request, url: str = Form(...), pdf: Optional[bool] = Form(False), session_email: Optional[str] = Cookie(None)):
    if not session_email:
        return RedirectResponse('/login', status_code=303)
    metrics = await run_audit(url)
    cats = compute_category_scores(metrics)
    overall_score, grade = compute_overall_score(cats)
    graphs = generate_graphs([metrics], STATIC_DIR, ['auto'], logger)
    pdf_path = None
    if pdf:
        pdf_path = maybe_generate_pdf([metrics], ARTIFACTS_DIR, logger) or fallback_pdf([metrics], graphs, ARTIFACTS_DIR, logger)
    return templates.TemplateResponse('audit_detail.html', {
        'request': request,
        'url': url,
        'category_scores': cats,
        'overall_score': round(overall_score, 2),
        'grade': grade,
        'graphs': [str(p) for p in graphs],
        'pdf_path': str(pdf_path) if pdf_path else None,
        'title': 'Audit Result'
    })

@app.get('/health')
async def health():
    return {'status': 'ok'}
