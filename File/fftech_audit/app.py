
# fftech_audit/app.py
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import FastAPI, Request, Form
from fastapi.responses import StreamingResponse
from starlette.responses import RedirectResponse
from starlette.templating import Jinja2Templates

from .audit_engine import AuditEngine, generate_pdf_report

logger = logging.getLogger("fftech")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

app = FastAPI(title="FFTech AI Website Audit SaaS")

templates = Jinja2Templates(directory="fftech_audit/templates")
templates.env.globals["len"] = len  # optional

engine = AuditEngine()

@app.get("/", include_in_schema=False)
async def index() -> RedirectResponse:
    # Redirect to /audit/open
    return RedirectResponse(url="/audit/open")

# ✅ Added GET handler to fix 405 error
@app.get("/audit/open")
async def audit_open_get(request: Request):
    """
    GET handler for /audit/open to display the audit form.
    This prevents 405 errors when redirected from '/'.
    """
    return templates.TemplateResponse("results.html", {
        "request": request,
        "url": None,
        "metrics": {},
        "rows": [],
    })

@app.post("/audit/open")
async def audit_open_post(request: Request, url: str = Form(...)) -> Any:
    """
    POST handler: executes the audit for the submitted URL and renders results.
    """
    logger.info("[POST /audit/open] Starting audit for %s", url)
    metrics: Dict[str, Any] = engine.run(url)
    rows = metrics.get("rows", [])
    logger.info("[POST /audit/open] Metrics OK (%s keys)", len(metrics))
    return templates.TemplateResponse("results.html", {
        "request": request,
        "url": url,
        "metrics": metrics,
        "rows": rows,
    })

@app.post("/audit/pdf")
async def audit_pdf(url: str = Form(...)) -> StreamingResponse:
    """
    Generate a 5-page, client-ready PDF for the given URL and return it.
    """
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
    return {"status": "ok"}
``
