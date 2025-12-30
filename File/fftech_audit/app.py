
# fftech_audit/app.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from datetime import datetime

from fastapi import FastAPI, Request, Form
from fastapi.responses import StreamingResponse
from starlette.templating import Jinja2Templates

from .audit_engine import AuditEngine, generate_pdf_report

# ---- Logging --------------------------------------------------------------
logger = logging.getLogger("fftech")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# ---- FastAPI app ----------------------------------------------------------
app = FastAPI(title="FFTech AI Website Audit SaaS")

# ---- Jinja templates ------------------------------------------------------
templates = Jinja2Templates(directory="fftech_audit/templates")
# Optional convenience; your templates use |length already, but keeping this does not hurt.
templates.env.globals["len"] = len

# ---- Engine ---------------------------------------------------------------
engine = AuditEngine()

# ---- Routes ---------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def index(request: Request):
    """
    Return a simple 200 OK page at root (no redirect) for platform health checks,
    and to show the audit form immediately.
    """
    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "url": None,
            "metrics": {},
            "rows": [],
            "now": datetime.utcnow(),
        },
    )

@app.get("/audit/open")
async def audit_open_get(request: Request, url: Optional[str] = None) -> Any:
    """
    GET: Show the audit form. If a query param ?url=... is provided, run the audit and show results.
    """
    if url:
        logger.info("[GET /audit/open] Running audit for %s", url)
        metrics: Dict[str, Any] = engine.run(url)
        rows = metrics.get("rows", [])
        return templates.TemplateResponse(
            "results.html",
            {
                "request": request,
                "url": url,
                "metrics": metrics,
                "rows": rows,
                "now": datetime.utcnow(),
            },
        )

    # No URL provided -> render form-only page
    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "url": None,
            "metrics": {},
            "rows": [],
            "now": datetime.utcnow(),
        },
    )

@app.post("/audit/open")
async def audit_open_post(request: Request, url: str = Form(...)) -> Any:
    """
    POST: Executes the audit for the submitted URL and renders results.
    """
    logger.info("[POST /audit/open] Starting audit for %s", url)
    metrics: Dict[str, Any] = engine.run(url)
    rows = metrics.get("rows", [])
    logger.info("[POST /audit/open] Metrics OK (%s keys)", len(metrics))

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "url": url,
            "metrics": metrics,
            "rows": rows,
            "now": datetime.utcnow(),
        },
    )

@app.post("/audit/pdf")
async def audit_pdf(url: str = Form(...)) -> StreamingResponse:
    """
    Generate a 5-page, client-ready PDF for the given URL and return it.
    """
    logger.info("[POST /audit/pdf] Generating PDF for %s", url)
    metrics = engine.run(url)
    rows = metrics.get("rows", [])
    pdf_bytes = generate_pdf_report(url=url, metrics=metrics, rows=rows)

    filename = f"FFTech_Audit_{url.replace('https://','').replace('http://','').replace('/','_')}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

@app.get("/health", include_in_schema=False)
async def health() -> Dict[str, str]:
    """
    Simple health endpoint (200 OK) for platform liveness checks.
    """
    return {"status": "ok"}
