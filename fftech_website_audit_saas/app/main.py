import datetime
import os
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .database import Base, engine, SessionLocal
from .models import User, Website, Subscription, Audit
from .auth import router as auth_router, get_user_id_from_token
from .schemas import WebsitePayload, SchedulePayload, AuditRunResponse
from .audit_engine import run_basic_audit, strict_score, generate_summary_200
from .pdf import render_certified_pdf
from .scheduler import schedule_daily_audit

app = FastAPI(title="FF Tech – AI Powered Website Audit SaaS")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auto-create database tables
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- ROUTES ---
app.include_router(auth_router)

# Serve the index.html from the 'frontend' folder
@app.get("/")
async def serve_frontend():
    # Make sure your file is at frontend/index.html
    return FileResponse('frontend/index.html')

def _get_user_id(request: Request, db: Session):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    return get_user_id_from_token(token, db)

# --- WEBSITES ---
@app.post("/websites")
def add_website(payload: WebsitePayload, request: Request, db: Session = Depends(get_db)):
    user_id = _get_user_id(request, db)
    w = Website(user_id=user_id, url=str(payload.url))
    db.add(w); db.commit(); db.refresh(w)
    return {"id": w.id, "url": w.url}

# --- RUN AUDIT ---
@app.post("/audits/{website_id}/run", response_model=AuditRunResponse)
def run_audit(website_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = _get_user_id(request, db)
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == user_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Website not found")
        
    metrics = run_basic_audit(w.url)
    score, grade = strict_score(metrics)
    summary = generate_summary_200(metrics, score, grade)
    
    a = Audit(website_id=w.id, started_at=datetime.datetime.utcnow(), 
              finished_at=datetime.datetime.utcnow(), grade=grade, 
              overall_score=score, summary_200_words=summary, json_metrics=metrics)
    db.add(a); db.commit(); db.refresh(a)
    return {"audit_id": a.id, "grade": grade, "score": score, "summary": summary}

@app.get("/audits/{audit_id}")
def audit_detail(audit_id: int, request: Request, db: Session = Depends(get_db)):
    a = db.query(Audit).filter(Audit.id == audit_id).first()
    return {"website": "Audit Results", "grade": a.grade, "score": a.overall_score, "summary": a.summary_200_words, "metrics": a.json_metrics}

@app.get("/reports/{audit_id}/pdf")
def report_pdf(audit_id: int, request: Request, db: Session = Depends(get_db)):
    path = f"/tmp/audit_{audit_id}.pdf"
    # Assuming render_certified_pdf is imported
    return {"pdf_path": path}
