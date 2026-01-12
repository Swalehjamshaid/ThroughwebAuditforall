
# app/main.py
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

from .db import engine, Base
from .routers import health, auth, audits, pages

app = FastAPI(title="FF Tech AI Website Audit SaaS", version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

TZ_OFFSET = timezone(timedelta(hours=5))

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

def common_context(request: Request, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {
        "request": request,
        "year": datetime.now(TZ_OFFSET).year,
    }
    if extra:
        ctx.update(extra)
    return ctx

# --- Index (kept) ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    ctx = {"metrics": {"total_audits": 128, "open_findings": 57, "avg_risk": 72}}
    return templates.TemplateResponse("index.html", common_context(request, ctx))

# --- NEW AUDIT: register all common variants ---
@app.get("/new_audit", response_class=HTMLResponse)
async def new_audit_underscore(request: Request):
    """Preferred route with underscore."""
    return templates.TemplateResponse("new_audit.html", common_context(request))

@app.get("/new_audit/", response_class=HTMLResponse)
async def new_audit_underscore_slash():
    """Normalize trailing slash to underscore route."""
    return RedirectResponse(url="/new_audit", status_code=307)

@app.get("/new-audit", response_class=HTMLResponse)
async def new_audit_hyphen(request: Request):
    """Support hyphen variant for convenience."""
    return templates.TemplateResponse("new_audit.html", common_context(request))

@app.get("/new-audit/", response_class=HTMLResponse)
async def new_audit_hyphen_slash():
    """Normalize trailing slash to hyphen route."""
    return RedirectResponse(url="/new-audit", status_code=307)

# --- Dashboard (optional, unchanged) ---
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    ctx = {
        "kpis": {
            "audits_this_month": 12,
            "closed_findings": 34,
            "high_risk": 7,
            "mean_closure_days": 9,
        },
        "recent_audits": [
            {"id": 101, "title": "Plant A Safety", "owner": "Ops", "status": "Open", "risk": 78, "updated": "2026-01-10"},
            {"id": 102, "title": "Data Center Security", "owner": "IT", "status": "In Progress", "risk": 65, "updated": "2026-01-09"},
            {"id": 103, "title": "Finance Controls", "owner": "Finance", "status": "Closed", "risk": 40, "updated": "2026-01-07"},
        ],
        "charts": {
            "trend": {"labels": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"], "values": [4, 6, 3, 8, 7, 9]},
            "severity": {"labels": ["Critical", "High", "Medium", "Low"], "values": [5, 12, 20, 8]},
            "top_owners": {"labels": ["Ops", "IT", "Finance", "HR"], "values": [22, 18, 12, 9]},
        },
    }
    return templates.TemplateResponse("dashboard.html", common_context(request, ctx))

# --- Auth pages (unchanged) ---
@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    return templates.TemplateResponse("login.html", common_context(request))

@app.get("/register", response_class=HTMLResponse)
async def register(request: Request):
    return templates.TemplateResponse("register.html", common_context(request))

@app.get("/verify", response_class=HTMLResponse)
async def verify(request: Request):
    return templates.TemplateResponse("verify.html", common_context(request))

# --- Existing routers ---
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(audits.router)
app.include_router(pages.router)
