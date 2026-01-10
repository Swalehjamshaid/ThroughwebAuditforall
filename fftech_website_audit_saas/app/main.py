
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

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / 'templates'
STATIC_DIR = BASE_DIR / 'static'
ARTIFACTS_DIR = DEFAULT_OUTPUT_DIR

logger, _ = setup_logging()

app = FastAPI(title='Audit SAAS', version='1.0.0')
app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

RUNS: Dict[str, Dict[str, Any]] = {}

for d in [TEMPLATES_DIR, STATIC_DIR, STATIC_DIR / 'img' / 'graphs', ARTIFACTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse('index.html', {
        'request': request,
        'title': 'Website Audit Runner',
    })

@app.post('/run', response_class=HTMLResponse)
async def run(
    request: Request,
    report: Optional[str] = Form(None),
    graph_types: Optional[str] = Form('auto'),
    input_path: Optional[str] = Form(None),
    pdf: Optional[bool] = Form(False),
):
    start = time.time()
    output_dir = ARTIFACTS_DIR
    report_path = discover_report_path(report, output_dir, logger)

    grade_all = import_grader(logger)
    results: Any = None
    if callable(grade_all) and input_path:
        try:
            results = grade_all(input_path=input_path, config={}, logger=logger)  # type: ignore
        except Exception as e:
            logger.error('Grade step failed: %s', e, exc_info=True)

    rows: List[Dict[str, Any]] = []
    if report_path:
        try:
            rows = load_report_data(report_path, logger)
        except Exception as e:
            logger.error('Failed to load report data: %s', e, exc_info=True)

    graphs = generate_graphs(rows, STATIC_DIR, (graph_types or 'auto').split(','), logger)

    pdf_path = None
    if pdf:
        pdf_path = maybe_generate_pdf(rows, output_dir, logger) or fallback_pdf(rows, graphs, output_dir, logger)

    run_id = str(uuid.uuid4())
    RUNS[run_id] = {
        'report_path': str(report_path) if report_path else None,
        'graphs': [str(p) for p in graphs],
        'pdf_path': str(pdf_path) if pdf_path else None,
        'duration': round(time.time() - start, 2),
    }

    return RedirectResponse(url=f'/report/{run_id}', status_code=303)

@app.get('/report/{run_id}', response_class=HTMLResponse)
async def report_page(request: Request, run_id: str):
    data = RUNS.get(run_id)
    if not data:
        return templates.TemplateResponse('base_open.html', {
            'request': request,
            'title': 'Not Found',
            'content': f'Run {run_id} not found.'
        })
    return templates.TemplateResponse('report.html', {
        'request': request,
        'title': 'Audit Report Output',
        'data': data,
    })

@app.get('/health')
async def health():
    return {'status': 'ok'}
