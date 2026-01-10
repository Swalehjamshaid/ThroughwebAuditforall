# app/main.py
# -*- coding: utf-8 -*-

import os
import uuid
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request, Form, Depends, HTTPException, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

# FF Tech Engine & Utilities
from .db import engine, SessionLocal, Base
from .models import User, Website, Audit, Subscription
from .auth import create_token, decode_token
from .audit.engine import run_audit  # Consuming the 200-metric engine
from .services.graph_service import generate_graphs
from .services.pdf_service import render_pdf_10p

# ---------- CONFIGURATION ----------
UI_BRAND_NAME = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL      = os.getenv("BASE_URL", "http://localhost:8000")

app = FastAPI(title=f"{UI_BRAND_NAME} AI Website Audit SaaS")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# In-memory store for Open Access results (Session-based)
OPEN_AUDITS: Dict[str, Dict[str, Any]] = {}

# ---------- DATABASE & AUTH HELPERS ----------
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

async def get_current_user(session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    if not session_token: return None
    try:
        data = decode_token(session_token)
        return db.query(User).filter(User.id == data.get("uid")).first()
    except: return None

# ---------- 1. OPEN ACCESS ROUTES (Functional Req 1.1) ----------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user: Optional[User] = Depends(get_current_user)):
    return templates.TemplateResponse("index.html", {
        "request": request, "brand": UI_BRAND_NAME, "user": user
    })

@app.post("/audit/open")
async def audit_open_post(url: str = Form(...), db: Session = Depends(get_db)):
    # Run the comprehensive 200-metric engine
    import logging
    logger = logging.getLogger("uvicorn")
    
    # Process the audit
    result = run_audit(url, logger)
    
    # Generate Run ID for result retrieval
    run_id = str(uuid.uuid4())
    OPEN_AUDITS[run_id] = result
    
    return RedirectResponse(url=f"/audit/report/{run_id}", status_code=303)

@app.get("/audit/report/{run_id}", response_class=HTMLResponse)
async def open_report_view(run_id: str, request: Request, user: Optional[User] = Depends(get_current_user)):
    data = OPEN_AUDITS.get(run_id)
    if not data: return RedirectResponse("/")
    
    return templates.TemplateResponse("audit_report.html", {
        "request": request,
        "brand": UI_BRAND_NAME,
        "user": user,
        "data": data,  # Pass the A-I categories directly to the frontend
        "title": f"Audit Report: {data['url']}"
    })

# ---------- 2. REGISTERED ACCESS & MAGIC LINK (Functional Req 1.2) ----------

@app.post("/auth/magic-link")
async def request_magic_link(email: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, verified=True)
        db.add(user); db.commit(); db.refresh(user)
    
    token = create_token({"uid": user.id, "type": "magic"}, expires_minutes=15)
    # email_service.send_magic_link(email, token) 
    print(f"DEBUG: Magic Link -> {BASE_URL}/auth/verify?token={token}")
    return {"status": "success", "message": "Magic link sent to your email."}

@app.get("/auth/verify")
async def verify_magic_link(token: str, db: Session = Depends(get_db)):
    try:
        data = decode_token(token)
        user = db.query(User).filter(User.id == data["uid"]).first()
        session_token = create_token({"uid": user.id}, expires_minutes=43200)
        
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(key="session_token", value=session_token, httponly=True)
        return response
    except:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user: return RedirectResponse("/")
    
    websites = db.query(Website).filter(Website.user_id == user.id).all()
    # Pull limits (Functional Req 2.0)
    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user, "websites": websites, 
        "brand": UI_BRAND_NAME, "plan": sub.plan if sub else "Free"
    })

# ---------- 3. CERTIFIED PDF GENERATION (Functional Req 3.0) ----------

@app.get("/report/pdf/{run_id}")
async def export_pdf(run_id: str):
    data = OPEN_AUDITS.get(run_id)
    if not data: raise HTTPException(status_code=404)
    
    # Generate graphs for the PDF (Section A, B, G)
    # 
    # graph_paths = generate_graphs(data, static_dir="app/static") 
    
    pdf_filename = f"{UI_BRAND_NAME}_Certified_Audit_{run_id[:8]}.pdf"
    pdf_path = f"/tmp/{pdf_filename}"
    
    render_pdf_10p(data, pdf_path, brand=UI_BRAND_NAME)
    
    return FileResponse(pdf_path, filename=pdf_filename, media_type="application/pdf")

# ---------- STARTUP ----------
@app.on_event("startup")
async def startup_event():
    Base.metadata.create_all(bind=engine)
