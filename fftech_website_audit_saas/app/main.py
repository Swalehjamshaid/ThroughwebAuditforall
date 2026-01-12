
from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .db import engine, Base, get_db
from .routers import health, auth, audits, pages
from .routers.auth import seed_admin
from .audit_engine import run_audit
from .report import build_report

APP_TITLE = "FF Tech AI Website Audit SaaS"
APP_VERSION = "1.0.0"
TZ_OFFSET = timezone(timedelta(hours=5))

app = FastAPI(title=APP_TITLE, version=APP_VERSION)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
EXPORT_DIR = BASE_DIR / "export"
EXPORT_DIR.mkdir(exist_ok=True)

app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.state.year = datetime.now(TZ_OFFSET).year

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.add_middleware(SessionMiddleware, secret_key=os.getenv('SECRET_KEY','change-me-secret'))

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    from sqlalchemy.orm import Session
    with next(get_db()) as db:  # type: ignore
        seed_admin(db)

# Helpers

def common_context(request: Request, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {"request": request, "year": app.state.year}
    if extra:
        ctx.update(extra)
    return ctx

# Pages
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    ctx = {"metrics": {"total_audits": 128, "open_findings": 57, "avg_risk": 72}}
    return app.state.templates.TemplateResponse("index.html", common_context(request, ctx))

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    ctx = {
        "kpis": {"audits_this_month": 12, "closed_findings": 34, "high_risk": 7, "mean_closure_days": 9},
        "recent_audits": [
            {"id": 101, "title": "Plant A Safety", "owner": "Ops", "status": "Open", "risk": 78, "updated": "2026-01-10"},
            {"id": 102, "title": "Data Center Security", "owner": "IT", "status": "In Progress", "risk": 65, "updated": "2026-01-09"},
            {"id": 103, "title": "Finance Controls", "owner": "Finance", "status": "Closed", "risk": 40, "updated": "2026-01-07"},
        ],
        "charts": {"trend": {"labels": ["Jan","Feb","Mar","Apr","May","Jun"], "values": [4,6,3,8,7,9]},
                    "severity": {"labels": ["Critical","High","Medium","Low"], "values": [5,12,20,8]},
                    "top_owners": {"labels": ["Ops","IT","Finance","HR"], "values": [22,18,12,9]},},
    }
    return app.state.templates.TemplateResponse("dashboard.html", common_context(request, ctx))

# Open Access audit (stateless)
@app.get("/open-audit", response_class=HTMLResponse)
async def open_audit(request: Request, url: str):
    if not url or "." not in url:
        raise HTTPException(status_code=400, detail="Please provide a valid website URL")
    result = run_audit(url)
    ctx = {
        "audit": {"title": f"Open Audit: {url}", "owner": "Public", "status": "Complete", "risk": result["overall_score"], "updated": datetime.now(TZ_OFFSET).strftime("%Y-%m-%d")},
        "findings": [{"id":"OA-01","title":"Missing structured data","severity":"Medium","status":"Open","owner":"SEO","due":"-"},
                      {"id":"OA-02","title":"Large image payloads","severity":"High","status":"Open","owner":"Ops","due":"-"}],
        "charts": result["charts"],
    }
    return app.state.templates.TemplateResponse("audit_detail.html", common_context(request, ctx))

# New audit form
@app.get("/new_audit", response_class=HTMLResponse)
async def new_audit_form(request: Request):
    return app.state.templates.TemplateResponse("new_audit.html", common_context(request))

@app.post("/new_audit", response_class=HTMLResponse)
async def new_audit_submit(request: Request, url: str = Form(...)):
    if not url or "." not in url:
        raise HTTPException(status_code=400, detail="Please provide a valid website URL")
    result = run_audit(url)
    artifacts = build_report(result, str(EXPORT_DIR))
    ctx = {
        "audit": {"title": f"Audit: {url}", "owner": "Public", "status": "Complete", "risk": result["overall_score"], "updated": datetime.now(TZ_OFFSET).strftime("%Y-%m-%d")},
        "findings": [{"id":"OA-01","title":"Missing structured data","severity":"Medium","status":"Open","owner":"SEO","due":"-"},
                      {"id":"OA-02","title":"Large image payloads","severity":"High","status":"Open","owner":"Ops","due":"-"}],
        "charts": result["charts"],
        "report_pdf": f"/download/report/{Path(artifacts['report_pdf']).name}",
    }
    return app.state.templates.TemplateResponse("audit_detail.html", common_context(request, ctx))

@app.get("/download/report/{filename}")
async def download_report(filename: str):
    path = EXPORT_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(path)

# Routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(audits.router)
app.include_router(pages.router)
