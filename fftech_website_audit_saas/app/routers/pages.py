
from __future__ import annotations
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Audit

router = APIRouter(tags=["pages"])
TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

ctx = {"year": datetime.utcnow().year}

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request, **ctx})

@router.get("/admin", response_class=HTMLResponse)
async def admin(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request, **ctx})

@router.get("/auth/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, **ctx})

@router.get("/auth/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, **ctx})

@router.get("/auth/verify", response_class=HTMLResponse)
async def verify_page(request: Request):
    return templates.TemplateResponse("verify.html", {"request": request, **ctx})

@router.get("/audits/new", response_class=HTMLResponse)
async def new_audit_page(request: Request):
    return templates.TemplateResponse("new_audit.html", {"request": request, **ctx})

@router.get("/audits/{audit_id}", response_class=HTMLResponse)
async def audit_detail_page(request: Request, audit_id: int):
    db: Session = SessionLocal()
    try:
        audit = db.query(Audit).filter(Audit.id == audit_id).first()
        return templates.TemplateResponse("audit_detail.html", {"request": request, "audit": audit, **ctx})
    finally:
        db.close()

@router.get("/audits/{audit_id}/open", response_class=HTMLResponse)
async def audit_detail_open_page(request: Request, audit_id: int):
    db: Session = SessionLocal()
    try:
        audit = db.query(Audit).filter(Audit.id == audit_id).first()
        return templates.TemplateResponse("audit_detail_open.html", {"request": request, "audit": audit, **ctx})
    finally:
        db.close()
