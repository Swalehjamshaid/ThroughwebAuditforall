
# app/main.py
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

from .db import engine, Base
from .routers import health, auth, audits, pages

# ------------------------------------------------------------------------------
# App setup
# ------------------------------------------------------------------------------
app = FastAPI(title="FF Tech AI Website Audit SaaS", version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Use GMT+05:00 as per your environment
TZ_OFFSET = timezone(timedelta(hours=5))

# ------------------------------------------------------------------------------
# Startup
# ------------------------------------------------------------------------------
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def common_context(request: Request, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Base context for all pages so templates always get required keys."""
    ctx: Dict[str, Any] = {
        "request": request,
        "year": datetime.now(TZ_OFFSET).year,
    }
    if extra:
        ctx.update(extra)
    return ctx

def sample_index_metrics() -> Dict[str, Any]:
    """Stubbed metrics for the index page (replace with DB or audit engine)."""
    return {
        "total_audits": 128,     # number of audits run on the platform
        "open_findings": 57,     # current open findings across audits
        "avg_risk": 72,          # average risk score in %
    }

# ------------------------------------------------------------------------------
# Pages (HTML routes)
# ------------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # FIX: provide `metrics` expected by templates/index.html
    ctx = {"metrics": sample_index_metrics()}
    return templates.TemplateResponse("index.html", common_context(request, ctx))

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    # Optional: keep dashboard working with charts/cards (if you have that page)
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

@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    return templates.TemplateResponse("login.html", common_context(request))

@app.get("/register", response_class=HTMLResponse)
async def register(request: Request):
    return templates.TemplateResponse("register.html", common_context(request))

@app.get("/verify", response_class=HTMLResponse)
async def verify(request: Request):
    return templates.TemplateResponse("verify.html", common_context(request))

# ------------------------------------------------------------------------------
# Existing routers
# ------------------------------------------------------------------------------
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(audits.router)
app.include_router(pages.router)
