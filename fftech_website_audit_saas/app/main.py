#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import uuid
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# FF Tech Service Imports
from .services.config import setup_logging, DEFAULT_OUTPUT_DIR
from .services.report_loader import discover_report_path, load_report_data
from .services.graph_service import generate_graphs
from .services.pdf_service import maybe_generate_pdf, fallback_pdf
from .services.external_imports import import_grader
from .services.engine_adapter import run_engine

# --- New SaaS Imports ---
# These are mapped to your new functional requirements
from .services.auth_service import create_magic_token, verify_magic_token
from .services.db_service import get_user_by_email, save_audit_history

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / 'templates'
STATIC_DIR = BASE_DIR / 'static'
ARTIFACTS_DIR = DEFAULT_OUTPUT_DIR

logger, _ = setup_logging()

# Brand Identity (Functional Req Part 1)
UI_BRAND_NAME = os.getenv("UI_BRAND_NAME", "FF Tech")

app = FastAPI(title=f'{UI_BRAND_NAME} AI Website Audit SaaS', version='3.0.0')
app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Persistence for Open Access vs Registered Mode
RUNS: Dict[str, Dict[str, Any]] = {}

# Ensure directory structure
for d in [TEMPLATES_DIR, STATIC_DIR, STATIC_DIR / 'img' / 'graphs', ARTIFACTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# --- 1. OPEN ACCESS ROUTES (Functional Req Part 1.1) ---

@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse('index.html', {
        'request': request,
        'title': f'{UI_BRAND_NAME} | AI-Powered Website Audit',
        'brand': UI_BRAND_NAME
    })

@app.post('/engine/run', response_class=HTMLResponse)
async def engine_run(
    request: Request,
    target: Optional[str] = Form(None),
    competitor: Optional[str] = Form(None), # Part 2 Category G
    graph_types: Optional[str] = Form('auto'),
    pdf: Optional[bool] = Form(False),
):
    start = time.time()
    
    # Run Audit (Category B-F)
    rows, produced_path = run_engine(target, ARTIFACTS_DIR, logger)
    
    # Run Competitor Comparison if provided (Category G)
    comp_rows = []
    if competitor:
        comp_rows, _ = run_engine(competitor, ARTIFACTS_DIR, logger)

    # Graphical presentation logic (Radar, Gauges, Heatmaps)
    # Extra data passed to graph_service for "World Best" presentation
    graphs = generate_graphs(
        rows, 
        STATIC_DIR, 
        (graph_types or 'auto').split(','), 
        logger,
        extra_data={'competitor_rows': comp_rows} if competitor else None
    )

    # 10-Page Certified PDF generation (Functional Req Part 3)
    pdf_path = None
    if pdf:
        pdf_path = maybe_generate_pdf(rows, ARTIFACTS_DIR, logger, is_certified=True)

    run_id = str(uuid.uuid4())
    RUNS[run_id] = {
        'source': 'engine',
        'target': target,
        'competitor': competitor,
        'graphs': [str(p).split('static/')[-1] for p in graphs], # Path fix for frontend
        'pdf_path': str(pdf_path) if pdf_path else None,
        'duration': round(time.time() - start, 2),
        'rows_count': len(rows),
        'health_score': rows[0].get('health_score', 0) if rows else 0
    }

    return RedirectResponse(url=f'/engine/report/{run_id}', status_code=303)

# --- 2. REGISTERED ACCESS ROUTES (Functional Req Part 1.2) ---

@app.get('/auth/login', response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse('login.html', {
        'request': request,
        'brand': UI_BRAND_NAME
    })

@app.post('/auth/magic-link')
async def request_magic_link(email: str = Form(...)):
    """Part 1.2: Passwordless Authentication logic."""
    token = create_magic_token(email)
    # Logic to send email would be called here
    logger.info(f"Magic link requested for {email}")
    return {"status": "success", "message": "Check your email for login link."}

@app.get('/auth/verify')
async def verify_login(token: str):
    email = verify_magic_token(token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired link.")
    
    # Set session and redirect to dashboard
    response = RedirectResponse(url='/dashboard', status_code=303)
    response.set_cookie(key="auth_user", value=email)
    return response

# --- 3. REPORTING & DASHBOARD ---

@app.get('/engine/report/{run_id}', response_class=HTMLResponse)
async def engine_report_page(request: Request, run_id: str):
    data = RUNS.get(run_id)
    if not data:
        return templates.TemplateResponse('base.html', {'request': request, 'content': 'Run not found.'})
    
    return templates.TemplateResponse('engine_report.html', {
        'request': request,
        'title': 'Executive Audit Results',
        'data': data,
        'brand': UI_BRAND_NAME
    })

@app.get('/dashboard', response_class=HTMLResponse)
async def dashboard(request: Request):
    """Part 1.2: Authenticated Dashboard."""
    user = request.cookies.get("auth_user")
    if not user:
        return RedirectResponse(url='/auth/login')
    
    return templates.TemplateResponse('dashboard.html', {
        'request': request,
        'user': user,
        'brand': UI_BRAND_NAME
    })

@app.get('/health')
async def health():
    return {'status': 'ok', 'brand': UI_BRAND_NAME, 'engine': 'active'}
