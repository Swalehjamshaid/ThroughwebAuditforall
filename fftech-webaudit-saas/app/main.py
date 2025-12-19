import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from .db import engine, session_scope
from .models import Base, User, AuditJob, AuditRun, CertifiedReport
from .auth import hash_password, verify_password, create_jwt, decode_jwt
from .audit.scheduler import start_scheduler, run_audit_for_job
from .admin.routes import router as admin_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="FF Tech – Website Audit SaaS")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Schemas ---
class RegisterIn(BaseModel):
    email: EmailStr
    password: str

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class AuditCreateIn(BaseModel):
    target_url: str
    schedule: str | None = None
    timezone: str | None = None

# --- Auth helpers ---
def get_user_from_token(authorization: str) -> User:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.replace('Bearer ', '')
    payload = decode_jwt(token)
    with session_scope() as s:
        user = s.get(User, payload.get('sub'))
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user

# --- Routes ---
@app.get('/health')
def health():
    return {"status": "ok"}

@app.post('/register')
def register(data: RegisterIn):
    with session_scope() as s:
        existing = s.execute(select(User).where(User.email == data.email)).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        user = User(email=data.email, password_hash=hash_password(data.password), email_verified=True)
        s.add(user)
        s.flush()
        # issue token
        token = create_jwt({"sub": user.id, "role": user.role})
        return {"token": token, "user_id": user.id}

@app.post('/login')
def login(data: LoginIn):
    with session_scope() as s:
        user = s.execute(select(User).where(User.email == data.email)).scalar_one_or_none()
        if not user or not verify_password(data.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        token = create_jwt({"sub": user.id, "role": user.role})
        return {"token": token}

@app.post('/audits')
def create_audit(data: AuditCreateIn, authorization: str | None = None):
    user = get_user_from_token(authorization)
    with session_scope() as s:
        job = AuditJob(owner_id=user.id, target_url=data.target_url, schedule=data.schedule, timezone=data.timezone or os.getenv('DEFAULT_TIMEZONE', 'UTC'))
        s.add(job)
        s.flush()
        if not data.schedule:
            # run immediately on-demand
            run_audit_for_job(job.id)
        return {"job_id": job.id}

@app.get('/audits/{job_id}')
def get_audit(job_id: int, authorization: str | None = None):
    user = get_user_from_token(authorization)
    with session_scope() as s:
        job = s.get(AuditJob, job_id)
        if not job or job.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Audit not found")
        runs = s.execute(select(AuditRun).where(AuditRun.job_id == job.id)).scalars().all()
        return {
            "job": {"id": job.id, "url": job.target_url, "schedule": job.schedule, "tz": job.timezone},
            "runs": [{"id": r.id, "status": r.status, "score": r.score, "grade": r.grade} for r in runs]
        }

@app.get('/reports/{run_id}/pdf')
def get_report_pdf(run_id: int, authorization: str | None = None):
    user = get_user_from_token(authorization)
    with session_scope() as s:
        run = s.get(AuditRun, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        job = s.get(AuditJob, run.job_id)
        if job.owner_id != user.id and user.role != 'admin':
            raise HTTPException(status_code=403, detail="Forbidden")
        report = s.execute(select(CertifiedReport).where(CertifiedReport.run_id == run.id)).scalar_one_or_none()
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        return {"pdf_path": report.pdf_path}

# Admin router
app.include_router(admin_router)

# Start scheduler (non-blocking)
try:
    start_scheduler()
except Exception:
    # Scheduler failures should not crash the app in containerized env
    pass
