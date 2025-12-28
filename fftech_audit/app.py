
# app.py
"""
FF Tech AI Website Audit SaaS — Main Entry Point
- Open Access & Registered Access (email-verified, passwordless)
- Free vs Pro plan (free: 10 audits; pro: scheduling & continuous monitoring)
- Professional 5-page PDF reports (ReportLab; via ui_and_pdf.py)
- 200 metrics & transparent scoring (via audit_engine.py)
- Single-page Web UI served from templates/index.html (frontend-agnostic)
- Health endpoint for Railway

Author: FF Tech
"""

import os, io, json, datetime
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr

# Functional modules
from db import SessionLocal, get_db, Base, engine, User, Audit, Schedule
from auth_email import (
    send_magic_link,
    verify_magic_link_and_issue_token,
    send_verification_code,
    verify_email_code_and_issue_token,
    verify_session_token,
    send_email_with_pdf,
)
from audit_engine import AuditEngine, METRIC_DESCRIPTORS, now_utc, is_valid_url
from ui_and_pdf import build_pdf_report

# ---------------- Config ----------------
APP_NAME = "FF Tech AI Website Audit SaaS"
PORT = int(os.getenv("PORT", "8080"))
FREE_AUDIT_LIMIT = 10

# ---------------- App ----------------
app = FastAPI(title=APP_NAME, version="3.0.0", description="Main entrypoint integrating DB, Auth, Metrics, UI & PDF")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
security = HTTPBearer()

# Ensure DB tables exist
Base.metadata.create_all(bind=engine)

# ---------------- Health ----------------
@app.get("/health")
def health():
    return {"status": "ok", "service": APP_NAME, "time": now_utc().isoformat()}

# ---------------- Schemas ----------------
class AuditRequest(BaseModel):
    url: str = Field(..., description="Website URL to audit")

class EmailRequest(BaseModel):
    email: EmailStr

class VerifyTokenRequest(BaseModel):
    token: str = Field(..., description="Magic-link token")

class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=4, max_length=8, description="Verification code (OTP) sent via email")

class ScheduleRequest(BaseModel):
    url: str
    frequency: str = Field(default="weekly", pattern="^(daily|weekly|monthly)$")  # Pydantic v2 compliant

# ---------------- Auth helpers ----------------
def auth_user(credentials: HTTPAuthorizationCredentials = Depends(security), db=Depends(get_db)) -> User:
    payload = verify_session_token(credentials.credentials)
    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Missing email in token")
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.verified:
        raise HTTPException(status_code=401, detail="User not verified")
    return user

# ---------------- Auth (Passwordless / Magic Link) ----------------
@app.post("/auth/request-link")
def request_magic_link(payload: EmailRequest, request: Request, db=Depends(get_db)):
    send_magic_link(payload.email, request, db)
    return {"message": "Login link sent (or logged on server for dev)."}

@app.post("/auth/verify-link")
def verify_magic(payload: VerifyTokenRequest, db=Depends(get_db)):
    token = verify_magic_link_and_issue_token(payload.token, db)
    return {"token": token}

# ---------------- Optional OTP flow ----------------
@app.post("/auth/request-code")
def request_code(payload: EmailRequest, request: Request, db=Depends(get_db)):
    send_verification_code(payload.email, request, db)
    return {"message": "Verification code sent (or logged on server for dev)."}

@app.post("/auth/verify-code")
def verify_code(payload: VerifyCodeRequest, db=Depends(get_db)):
    token = verify_email_code_and_issue_token(payload.email, payload.code, db)
    return {"token": token, "email": payload.email}

# ---------------- Open Access Audit ----------------
@app.post("/api/audit/open")
def audit_open(req: AuditRequest):
    if not is_valid_url(req.url):
        raise HTTPException(status_code=400, detail="Invalid URL")
    eng = AuditEngine(req.url)
    metrics = eng.compute_metrics()
    return {"mode": "open", "url": req.url, "score": metrics[1]["value"], "grade": metrics[2]["value"], "metrics": metrics}

# ---------------- Registered Audit (history stored) ----------------
@app.post("/api/audit/user")
def audit_user(req: AuditRequest, user: User = Depends(auth_user), db=Depends(get_db)):
    if not is_valid_url(req.url):
        raise HTTPException(status_code=400, detail="Invalid URL")
    if user.plan == "free" and user.audits_count >= FREE_AUDIT_LIMIT:
        raise HTTPException(status_code=402, detail="Free plan limit reached (10 audits). Upgrade for scheduling & long-term history.")

    eng = AuditEngine(req.url)
    metrics = eng.compute_metrics()
    a = Audit(user_id=user.id, url=req.url, metrics_json=json.dumps(metrics), score=metrics[1]["value"], grade=metrics[2]["value"])
    db.add(a)
    user.audits_count += 1
    db.commit()
    return {"mode": "registered", "audit_id": a.id, "url": req.url, "score": a.score, "grade": a.grade, "metrics": metrics}

# ---------------- History ----------------
@app.get("/api/audits")
def audits(limit: int = Query(20, ge=1, le=100), user: User = Depends(auth_user), db=Depends(get_db)):
    rows = db.query(Audit).filter(Audit.user_id == user.id).order_by(Audit.created_at.desc()).limit(limit).all()
    return [{"id": r.id, "url": r.url, "score": r.score, "grade": r.grade, "created_at": r.created_at.isoformat()} for r in rows]

# ---------------- Metrics Descriptors ----------------
@app.get("/api/metrics/descriptors")
def metrics_descriptors():
    return METRIC_DESCRIPTORS

# ---------------- PDF (registered) ----------------
@app.get("/api/report/{audit_id}.pdf")
def report_pdf_api(audit_id: int, user: User = Depends(auth_user), db=Depends(get_db)):
    a = db.query(Audit).filter(Audit.id == audit_id, Audit.user_id == user.id).first()
    if not a: raise HTTPException(status_code=404, detail="Audit not found")
    metrics = json.loads(a.metrics_json)
    pdf = build_pdf_report(a, metrics)
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="FFTech_Audit_{a.id}.pdf"'})

# ---------------- PDF (open, transient) ----------------
@app.post("/api/report/open.pdf")
def report_open_pdf(req: AuditRequest):
    if not is_valid_url(req.url):
        raise HTTPException(status_code=400, detail="Invalid URL")
    eng = AuditEngine(req.url)
    metrics = eng.compute_metrics()
    class _Transient:
        id = 0
        user_id = None
        url = req.url
        metrics_json = json.dumps(metrics)
        score = metrics[1]["value"]
        grade = metrics[2]["value"]
    pdf = build_pdf_report(_Transient, metrics)
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": 'attachment; filename="FFTech_Audit_Open.pdf"'})

# ---------------- Scheduling (Pro-only) ----------------
@app.post("/schedule")
def create_schedule(payload: ScheduleRequest, user: User = Depends(auth_user), db=Depends(get_db)):
    if user.plan == "free":
        raise HTTPException(status_code=402, detail="Scheduling requires subscription (Pro+).")
    freq = payload.frequency
    delta = datetime.timedelta(days=1 if freq=="daily" else 7 if freq=="weekly" else 30)
    sch = Schedule(user_id=user.id, url=payload.url, frequency=freq, enabled=True, next_run_at=now_utc()+delta)
    db.add(sch); db.commit()
    return {"message":"Scheduled", "schedule_id": sch.id}

@app.get("/schedule")
def list_schedules(user: User = Depends(auth_user), db=Depends(get_db)):
    rows = db.query(Schedule).filter(Schedule.user_id==user.id).order_by(Schedule.next_run_at).all()
    return [{"id": s.id, "url": s.url, "frequency": s.frequency, "enabled": s.enabled, "next_run_at": s.next_run_at.isoformat()} for s in rows]

@app.delete("/schedule/{schedule_id}")
def delete_schedule(schedule_id: int, user: User = Depends(auth_user), db=Depends(get_db)):
    s = db.query(Schedule).filter(Schedule.id==schedule_id, Schedule.user_id==user.id).first()
    if not s: raise HTTPException(status_code=404, detail="Schedule not found")
    db.delete(s); db.commit()
    return {"message": "Deleted"}

# Background loop for continuous monitoring & scheduled emails (SMTP must be configured)
async def scheduler_loop():
    while True:
        try:
            db = SessionLocal()
            now = now_utc()
            due = db.query(Schedule).filter(Schedule.enabled==True, Schedule.next_run_at <= now).all()
            for s in due:
                user = db.query(User).filter(User.id==s.user_id).first()
                if not user: continue
                try:
                    eng = AuditEngine(s.url)
                    metrics = eng.compute_metrics()
                    a = Audit(user_id=user.id, url=s.url, metrics_json=json.dumps(metrics), score=metrics[1]["value"], grade=metrics[2]["value"])
                    db.add(a); user.audits_count += 1
                    delta = datetime.timedelta(days=1 if s.frequency=="daily" else 7 if s.frequency=="weekly" else 30)
                    s.next_run_at = now + delta
                    db.commit()
                    # Email PDF (if SMTP configured)
                    pdf = build_pdf_report(a, metrics)
                    send_email_with_pdf(user.email, f"FF Tech Scheduled Audit: {s.url}", f"Attached is your scheduled audit PDF for {s.url}.", pdf, filename=f"FFTech_Audit_{a.id}.pdf")
                except Exception as e:
                    print(f"[Scheduler] Error auditing {s.url}: {e}")
            db.close()
        except Exception as e:
            print(f"[Scheduler] Loop error: {e}")
        import asyncio
        await asyncio.sleep(30)

@app.on_event("startup")
async def on_startup():
    import asyncio
    asyncio.create_task(scheduler_loop())

# ---------------- Single-page UI (templates/index.html) ----------------
@app.get("/", response_class=HTMLResponse)
def home():
    # Serve the template statically; JS fetches descriptors and calls APIs
    index_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse("<h2>templates/index.html not found</h2>", status_code=500)
    return FileResponse(index_path)

# ---------------- Run (local) ----------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
