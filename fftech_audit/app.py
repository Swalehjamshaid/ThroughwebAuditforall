
# fftech_audit/app.py
import os
import io
import json
import datetime
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, EmailStr

# ✅ Package-relative imports
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

# ---------------- Config ----------------
APP_NAME = "FF Tech AI Website Audit SaaS"
PORT = int(os.getenv("PORT", "8080"))
FREE_AUDIT_LIMIT = 10
SCHEDULER_SLEEP = int(os.getenv("SCHEDULER_INTERVAL", "60"))  # seconds

# ---------------- FastAPI App ----------------
app = FastAPI(
    title=APP_NAME,
    version="3.3.2",
    description="Main entrypoint integrating DB, Auth, Metrics, PDF & Scheduler"
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
security = HTTPBearer()

# ✅ Mount static from repo root: /static
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Ensure tables exist and fix schedules columns at startup
Base.metadata.create_all(bind=engine)
try:
    ensure_schedule_columns()
except Exception as e:
    print(f"[Startup] ensure_schedule_columns failed: {e}")

# ---------------- Health ----------------
@app.get("/health")
def health():
    return {"status": "ok", "service": APP_NAME, "time": now_utc().isoformat()}

# ---------------- Root: serve the template ----------------
@app.get("/", response_class=HTMLResponse)
def home():
    """
    Serve templates/index.html (world-class landing).
    """
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    if os.path.exists(template_path):
        # NOTE: FileResponse sets correct headers and streams file
        return FileResponse(template_path)
    return HTMLResponse("<h3>Template not found.</h3>", status_code=500)

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
    frequency: str = Field(default="weekly", pattern="^(daily|weekly|monthly)$")

# ---------------- Auth Helper ----------------
def auth_user(credentials: HTTPAuthorizationCredentials = Depends(security), db=Depends(get_db)) -> User:
    payload = verify_session_token(credentials.credentials)
    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Missing email in token")
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.verified:
        raise HTTPException(status_code=401, detail="User not verified")
    return user

# ---------------- Auth Routes ----------------
@app.post("/auth/request-link")
def request_magic_link(payload: EmailRequest, request: Request, db=Depends(get_db)):
    send_magic_link(payload.email, request, db)
    return {"message": "Login link sent (or logged on server for dev)."}

@app.post("/auth/verify-link")
def verify_magic(payload: VerifyTokenRequest, db=Depends(get_db)):
    token = verify_magic_link_and_issue_token(payload.token, db)
    return {"token": token}

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
    return {
        "mode": "open", "url": req.url,
        "score": metrics[1]["value"], "grade": metrics[2]["value"], "metrics": metrics
    }

# ---------------- Registered Audit ----------------
@app.post("/api/audit/user")
def audit_user(req: AuditRequest, user: User = Depends(auth_user), db=Depends(get_db)):
    if not is_valid_url(req.url):
        raise HTTPException(status_code=400, detail="Invalid URL")
    if user.plan == "free" and user.audits_count >= FREE_AUDIT_LIMIT:
        raise HTTPException(status_code=402, detail="Free plan limit reached (10 audits). Upgrade for scheduling & long-term history.")
    eng = AuditEngine(req.url)
    metrics = eng.compute_metrics()
    a = Audit(
        user_id=user.id, url=req.url,
        metrics_json=json.dumps(metrics), score=metrics[1]["value"], grade=metrics[2]["value"]
    )
    db.add(a)
    user.audits_count += 1
    db.commit()
    return {
        "mode": "registered", "audit_id": a.id, "url": req.url,
        "score": a.score, "grade": a.grade, "metrics": metrics
    }

# ---------------- History & Descriptors ----------------
@app.get("/api/audits")
def audits(limit: int = Query(20, ge=1, le=100), user: User = Depends(auth_user), db=Depends(get_db)):
    rows = db.query(Audit).filter(Audit.user_id == user.id).order_by(Audit.created_at.desc()).limit(limit).all()
    return [{"id": r.id, "url": r.url, "score": r.score, "grade": r.grade, "created_at": r.created_at.isoformat()} for r in rows]

@app.get("/api/metrics/descriptors")
def metrics_descriptors():
    return METRIC_DESCRIPTORS

# ---------------- PDF Endpoints ----------------
@app.get("/api/report/{audit_id}.pdf")
def report_pdf_api(audit_id: int, user: User = Depends(auth_user), db=Depends(get_db)):
    a = db.query(Audit).filter(Audit.id == audit_id, Audit.user_id == user.id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Audit not found")
    metrics = json.loads(a.metrics_json)
    pdf = build_pdf_report(a, metrics)
    return StreamingResponse(
        io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="FFTech_Audit_{a.id}.pdf"'}
    )

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
    return StreamingResponse(
        io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="FFTech_Audit_Open.pdf"'}
    )

# ---------------- Scheduler ----------------
async def scheduler_loop():
    while True:
        try:
            with SessionLocal() as db:
                now = now_utc()
                due = (
                    db.query(Schedule)
                      .filter(Schedule.enabled == True, Schedule.next_run_at <= now)
                      .limit(50)
                      .all()
                )
                for s in due:
                    user = db.query(User).filter(User.id == s.user_id).first()
                    if not user:
                        continue
                    try:
                        eng = AuditEngine(s.url)
                        metrics = eng.compute_metrics()

                        a = Audit(
                            user_id=user.id, url=s.url,
                            metrics_json=json.dumps(metrics),
                            score=metrics[1]["value"], grade=metrics[2]["value"]
                        )
                        db.add(a)

                        # Reschedule next run
                        delta = datetime.timedelta(days=1 if s.frequency == "daily" else 7 if s.frequency == "weekly" else 30)
                        s.next_run_at = now + delta
                        user.audits_count += 1

                        db.commit()

                        # Email PDF (best-effort)
                        try:
                            pdf = build_pdf_report(a, metrics)
                            send_email_with_pdf(
                                user.email,
                                f"FF Tech Scheduled Audit: {s.url}",
                                f"Attached is your scheduled audit PDF for {s.url}.",
                                pdf,
                                filename=f"FFTech_Audit_{a.id}.pdf"
                            )
                        except Exception as e:
                            print(f"[Scheduler] Email failed for {s.url}: {e}")

                    except Exception as e:
                        db.rollback()
                        if "UndefinedColumn" in str(e) and "schedules.url" in str(e):
                            try:
                                ensure_schedule_columns()
                                print("[Scheduler] Ran ensure_schedule_columns() after UndefinedColumn.")
                            except Exception as fix_e:
                                print(f"[Scheduler] Column fix failed: {fix_e}")
                        print(f"[Scheduler] Error auditing {s.url}: {e}")

        except Exception as e:
            print(f"[Scheduler] Loop error: {e}")

        import asyncio
        await asyncio.sleep(SCHEDULER_SLEEP)

@app.on_event("startup")
async def on_startup():
    import asyncio
    asyncio.create_task(scheduler_loop())

# ---------------- Run ----------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
