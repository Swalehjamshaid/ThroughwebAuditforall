
import os
import io
import json
import datetime
from typing import Dict, Any, List

from fastapi import FastAPI, HTTPException, Depends, Query, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, EmailStr

# package-relative imports
from .db import (
    SessionLocal, get_db, Base, engine,
    User, Audit, Schedule, ensure_schedule_columns
)
from .auth_email import (
    send_magic_link,
    verify_magic_link_and_issue_token,
    send_verification_code,
    verify_email_code_and_issue_token,
    verify_session_token,
    send_email_with_pdf,
)
from .audit_engine import AuditEngine, METRIC_DESCRIPTORS, now_utc, is_valid_url
from .ui_and_pdf import build_pdf_report

APP_NAME = "FF Tech AI Website Audit"
PORT = int(os.getenv("PORT", "8080"))
FREE_AUDIT_LIMIT = 10
SCHEDULER_SLEEP = int(os.getenv("SCHEDULER_INTERVAL", "60"))

app = FastAPI(title=APP_NAME, version="4.0", description="SSR + API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
security = HTTPBearer()

# mount static
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# jinja2 templates
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# DB init
Base.metadata.create_all(bind=engine)
try:
    ensure_schedule_columns()
except Exception as e:
    print(f"[Startup] ensure_schedule_columns failed: {e}")

# ---------------- Health ----------------
@app.get("/health")
def health():
    return {"status": "ok", "service": APP_NAME, "time": now_utc().isoformat()}

# ---------------- Landing (SSR) ----------------
@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "build_marker": "v2025-12-28-SSR-1"},
    )

# ---------------- Open Audit (SSR) ----------------
@app.post("/audit/open", response_class=HTMLResponse)
async def audit_open_ssr(request: Request, url: str = Form(...)):
    if not is_valid_url(url):
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": "Invalid URL", "prefill_url": url},
            status_code=400,
        )

    # run engine
    eng = AuditEngine(url)
    metrics: Dict[int, Dict[str, Any]] = eng.compute_metrics()  # {id: {value, detail}}

    # core items
    score = metrics[1]["value"]
    grade = metrics[2]["value"]
    summary = metrics[3]["value"]
    category = metrics[8]["value"]  # dict: Crawlability, On-Page SEO, Performance, Security, Mobile
    severity = metrics[7]["value"]  # dict: errors, warnings, notices

    # build rows (ID, Name, Category, Value, Detail) for SSR table
    rows: List[Dict[str, Any]] = []
    for pid in range(1, 201):
        desc = METRIC_DESCRIPTORS.get(pid, {"name": "(Unknown)", "category": "-"})
        cell = metrics.get(pid, {"value": "N/A", "detail": ""})
        val = cell["value"]
        val = json.dumps(val) if isinstance(val, (dict, list)) else val
        rows.append({
            "id": pid,
            "name": desc["name"],
            "category": desc["category"],
            "value": val,
            "detail": cell.get("detail", "")
        })

    # show pdf button for registered only (open users false)
    allow_pdf = False

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "url": url,
            "score": score,
            "grade": grade,
            "summary": summary,
            "severity": severity,
            "category": category,
            "rows": rows,
            "allow_pdf": allow_pdf,
            "build_marker": "v2025-12-28-SSR-1",
        },
    )

# ---------------- PDF (Open snapshot via POST, backend already supports) ----------------
@app.post("/api/report/open.pdf")
def report_open_pdf_api(req: Dict[str, str]):
    url = req.get("url")
    if not url or not is_valid_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL")
    eng = AuditEngine(url)
    metrics = eng.compute_metrics()

    class _Transient:
        id = 0
        user_id = None
        url = url
        metrics_json = json.dumps(metrics)
        score = metrics[1]["value"]
        grade = metrics[2]["value"]

    pdf = build_pdf_report(_Transient, metrics)
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="FFTech_Audit_Open.pdf"'},
    )
