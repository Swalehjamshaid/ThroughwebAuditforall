import datetime
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .config import CORS_ALLOW_ORIGINS
from .database import Base, engine, SessionLocal
from .models import User, Website, Subscription, Audit
from .auth import router as auth_router, get_user_id_from_token
from .schemas import WebsitePayload, SchedulePayload, AuditRunResponse
from .audit_engine import run_basic_audit, strict_score, generate_summary_200
from .pdf import render_certified_pdf
from .scheduler import schedule_daily_audit

app = FastAPI(title="FF Tech – AI Powered Website Audit SaaS")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ALLOW_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

Base.metadata.create_all(bind=engine)

# Dependency

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app.include_router(auth_router)

# Helper: Auth from header

def _get_user_id(request: Request, db: Session):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    return get_user_id_from_token(token, db)

# Websites
@app.post("/websites")
def add_website(payload: WebsitePayload, request: Request, db: Session = Depends(get_db)):
    user_id = _get_user_id(request, db)
    w = Website(user_id=user_id, url=str(payload.url))
    db.add(w); db.commit(); db.refresh(w)
    return {"id": w.id, "url": w.url}

@app.get("/websites")
def list_websites(request: Request, db: Session = Depends(get_db)):
    user_id = _get_user_id(request, db)
    ws = db.query(Website).filter(Website.user_id == user_id).all()
    return [{"id": w.id, "url": w.url, "active": w.active} for w in ws]

# Run audit
@app.post("/audits/{website_id}/run", response_model=AuditRunResponse)
def run_audit(website_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = _get_user_id(request, db)
    sub = db.query(Subscription).filter(Subscription.user_id == user_id, Subscription.status == "active").first()
    if sub and sub.plan == "free" and sub.quota_used >= sub.quota_limit:
        raise HTTPException(status_code=402, detail="Free plan limit reached. Please subscribe ($5/month).")
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == user_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Website not found")
    started = datetime.datetime.utcnow()
    metrics = run_basic_audit(w.url)
    score, grade = strict_score(metrics)
    summary = generate_summary_200(metrics, score, grade)
    a = Audit(website_id=w.id, started_at=started, finished_at=datetime.datetime.utcnow(), grade=grade, overall_score=score, summary_200_words=summary, json_metrics=metrics)
    db.add(a)
    if sub:
        sub.quota_used += 1; db.add(sub)
    db.commit(); db.refresh(a)
    return {"audit_id": a.id, "grade": grade, "score": score, "summary": summary}

@app.get("/audits/{audit_id}")
def audit_detail(audit_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = _get_user_id(request, db)
    a = db.query(Audit).filter(Audit.id == audit_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Audit not found")
    w = db.query(Website).filter(Website.id == a.website_id).first()
    if w.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"website": w.url, "grade": a.grade, "score": a.overall_score, "summary": a.summary_200_words, "metrics": a.json_metrics}

@app.get("/reports/{audit_id}/pdf")
def report_pdf(audit_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = _get_user_id(request, db)
    a = db.query(Audit).filter(Audit.id == audit_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Audit not found")
    w = db.query(Website).filter(Website.id == a.website_id).first()
    if w.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    path = f"/tmp/audit_{audit_id}.pdf"
    render_certified_pdf(path, w.url, a.grade, a.overall_score, a.finished_at.isoformat(), logo_path=None)
    return {"pdf_path": path}

# Scheduling
@app.post("/audits/{website_id}/schedule")
def schedule_audit(website_id: int, payload: SchedulePayload, request: Request, db: Session = Depends(get_db)):
    user_id = _get_user_id(request, db)
    u = db.query(User).filter(User.id == user_id).first()
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == user_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Website not found")
    job_id = f"audit-{user_id}-{website_id}"
    schedule_daily_audit(u.timezone or "UTC", job_id, payload.hour_local, payload.minute_local, website_id)
    return {"message": "Daily audit scheduled", "job_id": job_id}
