
import os, io, json, datetime
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, Depends, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, EmailStr

from .db import SessionLocal, get_db, Base, engine, User, Audit, Schedule, ensure_schedule_columns
from .auth_email import send_magic_link, verify_magic_link_and_issue_token, send_verification_code, verify_email_code_and_issue_token, verify_session_token, send_email_with_pdf
from .audit_engine import AuditEngine, METRIC_DESCRIPTORS, now_utc, is_valid_url
from .ui_and_pdf import build_pdf_report

APP_NAME = "FF Tech AI Website Audit"
PORT = int(os.getenv("PORT", "8080"))
FREE_AUDIT_LIMIT = 10
SCHEDULER_SLEEP = int(os.getenv("SCHEDULER_INTERVAL", "60"))

app = FastAPI(title=APP_NAME, version="1.0", description="Website Audit SaaS")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
security = HTTPBearer()

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

Base.metadata.create_all(bind=engine)
try:
    ensure_schedule_columns()
except Exception as e:
    print(f"[Startup] ensure_schedule_columns failed: {e}")

@app.get("/health")
def health():
    return {"status": "ok", "service": APP_NAME, "time": now_utc().isoformat()}

@app.get("/", response_class=HTMLResponse)
def home():
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    return FileResponse(template_path)

class AuditRequest(BaseModel):
    url: str

class EmailRequest(BaseModel):
    email: EmailStr

class VerifyTokenRequest(BaseModel):
    token: str

class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=4, max_length=8)

class ScheduleRequest(BaseModel):
    url: str
    frequency: str = Field(default="weekly", pattern="^(daily|weekly|monthly)$")

def auth_user(credentials: HTTPAuthorizationCredentials = Depends(security), db=Depends(get_db)) -> User:
    payload = verify_session_token(credentials.credentials)
    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Missing email in token")
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.verified:
        raise HTTPException(status_code=401, detail="User not verified")
    return user

@app.post("/auth/request-link")
def request_magic_link(payload: EmailRequest, request: Request, db=Depends(get_db)):
    send_magic_link(payload.email, request, db)
    return {"message": "Login link sent."}

@app.post("/auth/verify-link")
def verify_magic(payload: VerifyTokenRequest, db=Depends(get_db)):
    token = verify_magic_link_and_issue_token(payload.token, db)
    return {"token": token}

@app.post("/auth/request-code")
def request_code(payload: EmailRequest, request: Request, db=Depends(get_db)):
    send_verification_code(payload.email, request, db)
    return {"message": "Verification code sent."}

@app.post("/auth/verify-code")
def verify_code(payload: VerifyCodeRequest, db=Depends(get_db)):
    token = verify_email_code_and_issue_token(payload.email, payload.code, db)
    return {"token": token, "email": payload.email}

@app.post("/api/audit/open")
def audit_open(req: AuditRequest):
    if not is_valid_url(req.url):
        raise HTTPException(status_code=400, detail="Invalid URL")
    eng = AuditEngine(req.url)
    metrics = eng.compute_metrics()
    return {"mode":"open","url":req.url,"score":metrics[1]["value"],"grade":metrics[2]["value"],"metrics":metrics}
