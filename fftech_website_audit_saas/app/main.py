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

# FF Tech Service Imports - Refined for Package Stability
try:
    from .services.config import setup_logging, DEFAULT_OUTPUT_DIR
    from .services.report_loader import discover_report_path, load_report_data
    from .services.graph_service import generate_graphs
    from .services.pdf_service import maybe_generate_pdf, fallback_pdf
    from .services.external_imports import import_grader
    from .services.engine_adapter import run_engine
    from .services.auth_service import create_magic_token, verify_magic_token
except ImportError as e:
    # Fallback for direct execution contexts
    import sys
    print(f"IMPORT ERROR: {e}. Ensure you run from the project root.")
    raise

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / 'templates'
STATIC_DIR = BASE_DIR / 'static'
ARTIFACTS_DIR = DEFAULT_OUTPUT_DIR

logger, _ = setup_logging()
UI_BRAND_NAME = os.getenv("UI_BRAND_NAME", "FF Tech")

# Initialize FastAPI
app = FastAPI(title=f'{UI_BRAND_NAME} AI Website Audit SaaS', version='3.0.0')

# Mount Static Files
app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

RUNS: Dict[str, Dict[str, Any]] = {}

# Ensure directory structure exists on startup
for d in [TEMPLATES_DIR, STATIC_DIR, STATIC_DIR / 'img' / 'graphs', ARTIFACTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# --- 1. OPEN ACCESS ROUTES ---

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
    competitor: Optional[str] = Form(None),
    graph_types: Optional[str] = Form('auto'),
    pdf: Optional[bool] = Form(False),
):
    start = time.time()
    
    # Run the Engine (Categories B-F)
    # This calls the module that was causing the error
    rows, produced_path = run_engine(target, ARTIFACTS_DIR, logger)
    
    # Category G: Competitor Logic
    comp_rows = []
    if competitor:
        comp_rows, _ = run_engine(competitor, ARTIFACTS_DIR, logger)

    # World-Class Graphical Data Generation
    graphs = generate_graphs(
        rows, 
        STATIC_DIR, 
        (graph_types or 'auto').split(','), 
        logger,
        extra_data={'competitor_rows': comp_rows} if competitor else None
    )

    # 10-Page Certified PDF Logic (Category A.10)
    pdf_path = None
    if pdf:
        pdf_path = maybe_generate_pdf(rows, ARTIFACTS_DIR, logger)

    run_id = str(uuid.uuid4())
    RUNS[run_id] = {
        'source': 'engine',
        'target': target,
        'competitor': competitor,
        'graphs': [str(p).split('static/')[-1] for p in graphs],
        'pdf_path': str(pdf_path) if pdf_path else None,
        'duration': round(time.time() - start, 2),
        'rows_count': len(rows),
    }

    return RedirectResponse(url=f'/engine/report/{run_id}', status_code=303)

# --- 2. AUTHENTICATION (Magic Link Mode) ---

@app.post('/auth/magic-link')
async def request_magic_link(email: str = Form(...)):
    token = create_magic_token(email)
    logger.info(f"Magic link generated for {email}")
    # Integration point for SMTP service
    return {"status": "success", "message": "Link sent to email."}

# --- 3. SYSTEM HEALTH ---

@app.get('/health')
async def health():
    return {'status': 'ok', 'brand': UI_BRAND_NAME, 'engine': 'ready'}
