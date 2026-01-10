#!/usr/bin/env python3
"""
FFTech Website Audit SaaS - Main FastAPI Application
Central entry point for website auditing service with HTML interface and PDF reports
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Local imports - adjust according to your folder structure
from app.services.config import setup_logging, DEFAULT_OUTPUT_DIR
from app.services.report_loader import discover_report_path, load_report_data
from app.services.graph_service import generate_graphs
from app.services.pdf_service import render_pdf  # ← updated modern PDF renderer
from app.services.external_imports import import_grader

# ─── Paths & Configuration ──────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
GRAPHS_DIR = STATIC_DIR / "img" / "graphs"

# Output directory (Railway persistent volume recommended)
ARTIFACTS_DIR = DEFAULT_OUTPUT_DIR

# Create required directories
for directory in [TEMPLATES_DIR, STATIC_DIR, GRAPHS_DIR, ARTIFACTS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# ─── Application Setup ──────────────────────────────────────────────────────────
logger, _ = setup_logging()

app = FastAPI(
    title="FFTech Website Audit SaaS",
    description="Professional website performance, SEO, accessibility & security audit service",
    version="1.1.0",
    docs_url="/docs" if os.getenv("ENV") != "production" else None,
    redoc_url=None,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# In-memory storage for completed runs (consider Redis/DB for production)
RUNS: Dict[str, Dict[str, Any]] = {}


# ─── Helper Functions ───────────────────────────────────────────────────────────
def get_latest_run() -> Optional[Dict[str, Any]]:
    """Get most recent completed audit run."""
    if not RUNS:
        return None
    return max(RUNS.values(), key=lambda x: x.get("timestamp", 0))


# ─── Routes ─────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": "FFTech Website Audit",
            "current_year": datetime.now().year,
        }
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": "Dashboard",
            "latest": get_latest_run(),
        }
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html", {"request": request, "title": "Login"}
    )


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(
        "register.html", {"request": request, "title": "Register"}
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse(
        "admin.html", {"request": request, "title": "Admin Panel"}
    )


@app.get("/audit/detail", response_class=HTMLResponse)
async def audit_detail(request: Request):
    return templates.TemplateResponse(
        "audit_detail.html",
        {
            "request": request,
            "title": "Latest Audit Detail",
            "data": get_latest_run(),
        }
    )


@app.post("/run", response_class=HTMLResponse)
async def run_audit(
    request: Request,
    url: Optional[str] = Form(None, description="Website URL to audit"),
    report: Optional[str] = Form(None, description="Existing report filename"),
    graph_types: str = Form("auto", description="Comma-separated graph types or 'auto'"),
    generate_pdf: bool = Form(False, description="Generate PDF report"),
):
    """
    Start new audit process
    Accepts either fresh URL or existing report name
    """
    start_time = time.time()

    if not url and not report:
        raise HTTPException(
            status_code=400,
            detail="Either 'url' or 'report' parameter is required"
        )

    input_path = url  # for clarity

    # ── 1. Grading / Analysis step ───────────────────────────────────────
    results = None
    grade_all = import_grader(logger)
    if callable(grade_all) and input_path:
        try:
            results = grade_all(input_path=input_path, config={}, logger=logger)
            logger.info(f"Grading completed for: {input_path}")
        except Exception as e:
            logger.error("Grading failed", exc_info=True)

    # ── 2. Load existing report if requested ─────────────────────────────
    report_path = discover_report_path(report, ARTIFACTS_DIR, logger)
    rows: List[Dict[str, Any]] = []
    if report_path:
        try:
            rows = load_report_data(report_path, logger)
        except Exception as e:
            logger.error("Failed to load existing report data", exc_info=True)

    # ── 3. Generate graphs ───────────────────────────────────────────────
    graph_paths = generate_graphs(
        rows=rows,
        static_dir=STATIC_DIR,
        graph_types=(graph_types or "auto").split(","),
        logger=logger
    )

    # ── 4. Optional PDF generation ───────────────────────────────────────
    pdf_path = None
    if generate_pdf:
        pdf_path = render_pdf(
            rows=rows,
            output_dir=ARTIFACTS_DIR,
            logger=logger,
            website_url=input_path,
            overall_score=85.5,  # ← replace with real calculation when available
            overall_grade="B+"
        )

    # ── 5. Store run result ──────────────────────────────────────────────
    run_id = str(uuid.uuid4())
    RUNS[run_id] = {
        "run_id": run_id,
        "timestamp": time.time(),
        "input_url": input_path,
        "report_path": str(report_path) if report_path else None,
        "graphs": [str(p.relative_to(STATIC_DIR)) for p in graph_paths],
        "pdf_path": str(pdf_path.relative_to(ARTIFACTS_DIR)) if pdf_path else None,
        "duration_seconds": round(time.time() - start_time, 2),
        "rows_preview": rows[:80],  # limited to prevent memory issues
    }

    logger.info(f"Audit run completed - ID: {run_id} Duration: {run_id['duration_seconds']}s")

    return RedirectResponse(url=f"/report/{run_id}", status_code=303)


@app.get("/report/{run_id}", response_class=HTMLResponse)
async def view_report(request: Request, run_id: str):
    data = RUNS.get(run_id)
    if not data:
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "title": "Report Not Found",
                "message": f"No audit run found with ID: {run_id}"
            }
        )

    return templates.TemplateResponse(
        "report.html",
        {
            "request": request,
            "title": "Audit Report",
            "data": data,
        }
    )


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "service": "fftech-audit-saas",
        "timestamp": datetime.utcnow().isoformat(),
        "runs_count": len(RUNS),
        "artifacts_dir": str(ARTIFACTS_DIR),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=os.getenv("ENV") != "production"
    )
