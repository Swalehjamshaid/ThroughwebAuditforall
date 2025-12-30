
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
    return RedirectResponse(url="/audit/open")

@app.post("/audit/open")
async def audit_open(request: Request, url: str = Form(...)) -> Any:
    logger.info("[/audit/open] Starting audit for %s", url)
    metrics: Dict[str, Any] = engine.run(url)
    rows = metrics.get("rows", [])
    logger.info("[/audit/open] Metrics OK (%s keys)", len(metrics))
    return templates.TemplateResponse("results.html", {
        "request": request,
        "url": url,
        "metrics": metrics,
        "rows": rows,
    })

@app.post("/audit/pdf")
async def audit_pdf(url: str = Form(...)) -> StreamingResponse:
    metrics = engine.run(url)
    rows = metrics.get("rows", [])
    pdf_bytes = generate_pdf_report(url=url, metrics=metrics, rows=rows)
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=FFTech_Audit_{url.replace('https://','').replace('http://','').replace('/','_')}.pdf"},
    )

@app.get("/health", include_in_schema=False)
async def health() -> Dict[str, str]:
    return {"status": "ok"}
