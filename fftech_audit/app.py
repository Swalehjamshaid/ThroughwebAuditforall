
# fftech_audit/app.py
import os
import io
import json
import datetime
import threading
import time
from typing import Dict, Any, List

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Depends, Query, Request, Form, Body
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .db import (
    SessionLocal, get_db, Base, engine,
    User, Audit, Schedule, ensure_schedule_columns, ensure_user_columns
)
from .auth_email import (
    send_verification_link,
    verify_magic_or_verify_link,
    verify_session_token,
    hash_password,
    verify_password,
    send_email_with_pdf,
    generate_token,
)
from .audit_engine import AuditEngine, METRIC_DESCRIPTORS, now_utc, is_valid_url
from .ui_and_pdf import build_pdf_report

# ✅ Create FastAPI app FIRST
app = FastAPI(title="FF Tech AI Website Audit", version="4.0", description="SSR + API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
security = HTTPBearer()

# ✅ Mount static files
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ✅ Templates
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ✅ DB init
Base.metadata.create_all(bind=engine)
try:
    ensure_schedule_columns()
    ensure_user_columns()
except Exception as e:
    print(f"[Startup] ensure_* failed: {e}")

# ✅ Health check
@app.get("/health")
def health():
    return {"status": "ok", "service": "FF Tech AI Website Audit", "time": now_utc().isoformat()}

# ✅ Landing page
@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "build_marker": "v2025-12-28-SSR-4"})

# ✅ Open Audit (SSR)
@app.post("/audit/open", response_class=HTMLResponse)
async def audit_open_ssr(request: Request, url: str = Form(...)):
    if not is_valid_url(url):
        return templates.TemplateResponse("index.html", {"request": request, "error": "Invalid URL", "prefill_url": url}, status_code=400)
    try:
        eng = AuditEngine(url)
        metrics = eng.compute_metrics()
    except Exception as e:
        return templates.TemplateResponse("index.html", {"request": request, "error": f"Audit failed: {e}", "prefill_url": url}, status_code=500)

    score = metrics[1]["value"]
    grade = metrics[2]["value"]
    summary = metrics[3]["value"]
    category = metrics[8]["value"]
    severity = metrics[7]["value"]

    # ✅ Convert dict/list values to JSON strings for clean rendering
    rows = []
    for pid in range(1, 201):
        desc = METRIC_DESCRIPTORS.get(pid, {"name": "(Unknown)", "category": "-"})
        cell = metrics.get(pid, {"value": "N/A", "detail": ""})
        val = cell["value"]
        if isinstance(val, (dict, list)):
            val = json.dumps(val, ensure_ascii=False)
        rows.append({"id": pid, "name": desc["name"], "category": desc["category"], "value": val, "detail": cell.get("detail", "")})

    return templates.TemplateResponse("results.html", {
        "request": request,
        "url": url,
        "score": score,
        "grade": grade,
        "summary": summary,
        "severity": severity,
        "category": category,
        "rows": rows,
        "allow_pdf": False,
        "build_marker": "v2025-12-28-SSR-4",
    })
