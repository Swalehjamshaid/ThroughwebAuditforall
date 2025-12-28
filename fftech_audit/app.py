
# fftech_audit/app.py
import os
import io
import json
import datetime
import threading
import time
from typing import Dict, Any, List

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Depends, Query, Request, Form, Body
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .db import (
    SessionLocal, get_db, Base, engine,
    User, Audit, Schedule, ensure_schedule_columns, ensure_user_columns
)
from .auth_email import (
    send_verification_link,
    verify_magic_or_verify_link,
    send_verification_code,
    verify_email_code_and_issue_token,
    verify_session_token,
    hash_password,
    verify_password,
    send_email_with_pdf,
    generate_token,
)
from .audit_engine import AuditEngine, METRIC_DESCRIPTORS, now_utc, is_valid_url
from .ui_and_pdf import build_pdf_report

APP_NAME = "FF Tech AI Website Audit"
PORT = int(os.getenv("PORT", "8080"))
FREE_AUDIT_LIMIT = int(os.getenv("FREE_AUDITS_LIMIT", "10"))
SCHEDULER_SLEEP = int(os.getenv("SCHEDULER_INTERVAL", "60"))

app = FastAPI(title=APP_NAME, version="4.0", description="SSR + API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
security = HTTPBearer()

# ---------------- Static ----------------
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ---------------- Templates ----------------
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ---------------- DB init ----------------
Base.metadata.create_all(bind=engine)
try:
    ensure_schedule_columns()
    ensure_user_columns()
except Exception as e:
    print(f"[Startup] ensure_* failed: {e}")

# ---------------- Health ----------------
@app.get("/health")
def health():
    return {"status": "ok", "service": APP_NAME, "time": now_utc().isoformat()}

# ---------------- Landing (SSR) ----------------
@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "build_marker": "v2025-12-28-SSR-2"},
    )

# ---------------- Open Audit (SSR) ----------------
@app.post("/audit/open", response_class=HTMLResponse)
async def audit_open_ssr(request: Request, url: str = Form(...)):
    if not is_valid_url(url):
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": "Invalid URL", "prefill_url": url},
            status_code=400,
        )

    eng = AuditEngine(url)
    metrics: Dict[int, Dict[str, Any]] = eng.compute_metrics()

    score = metrics[1]["value"]
    grade = metrics[2]["value"]
    summary = metrics[3]["value"]
    category = metrics[8]["value"]
    severity = metrics[7]["value"]

    rows: List[Dict[str, Any]] = []
    for pid in range(1, 201):
        desc = METRIC_DESCRIPTORS.get(pid, {"name": "(Unknown)", "category": "-"})
        cell = metrics.get(pid, {"value": "N/A", "detail": ""})
        rows.append({
            "id": pid,
            "name": desc["name"],
            "category": desc["category"],
            "value": cell["value"],
            "detail": cell.get("detail", "")
        })

    allow_pdf = False  # Open users cannot download
    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "url": url,
            "score": score,
            "grade": grade,
            "summary": summary,
            "severity": severity,
            "category": category,
            "rows": rows,
            "allow_pdf": allow_pdf,
            "build_marker": "v2025-12-28-SSR-2",
        },
    )

# ---------------- API: audit open (JSON) ----------------
@app.post("/api/audit/open")
def api_audit_open(payload: Dict[str, str] = Body(...)):
    url = payload.get("url")
    if not url or not is_valid_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL")

    eng = AuditEngine(url)
    metrics = eng.compute_metrics()
    score = metrics[1]["value"]
    grade = metrics[2]["value"]

    db = next(get_db())
    audit = Audit(user_id=None, url=url, metrics_json=json.dumps(metrics), score=score, grade=grade)
    db.add(audit); db.commit()

    return {"url": url, "score": score, "grade": grade, "metrics": metrics}

# ---------------- API: metric descriptors ----------------
@app.get("/api/metrics/descriptors")
def api_metric_descriptors():
    return METRIC_DESCRIPTORS

# ---------------- PDF (Open snapshot via POST; dev only) ----------------
@app.post("/api/report/open.pdf")
def report_open_pdf_api(req: Dict[str, str]):
    url = req.get("url")
    if not url or not is_valid_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL")

    eng = AuditEngine(url)
    metrics = eng.compute_metrics()

    class _Transient:
        id = 0
        user_id = None
        url = url
        metrics_json = json.dumps(metrics)
        score = metrics[1]["value"]
        grade = metrics[2]["value"]

    pdf = build_pdf_report(_Transient, metrics)
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="FFTech_Audit_Open.pdf"'},
    )

# ---------------- Auth helpers ----------------
def require_user(credentials: HTTPAuthorizationCredentials = Depends(security),
                 db: Session = Depends(get_db)) -> User:
    payload = verify_session_token(credentials.credentials)
    email = payload.get("email")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.verified:
        raise HTTPException(status_code=403, detail="Email not verified")
    return user

# ---------------- Registration (SSR) ----------------
@app.get("/auth/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/auth/register", response_class=HTMLResponse)
def auth_register(request: Request,
                  name: str = Form(...),
                  email: str = Form(...),
                  password: str = Form(...),
                  db: Session = Depends(get_db)):
    email = email.strip().lower()
    name = name.strip()
    if not (name and email and password):
        return templates.TemplateResponse("register.html",
            {"request": request, "error": "Please fill in all fields."}, status_code=400)
    user = db.query(User).filter(User.email == email).first()
    if user and user.password_hash:
        return templates.TemplateResponse("register.html",
            {"request": request, "error": "Email already registered."}, status_code=400)
    if not user:
        user = User(name=name, email=email, password_hash=hash_password(password), verified=False, plan="free")
        db.add(user); db.commit()
    else:
        user.name = name
        user.password_hash = hash_password(password)
        user.verified = False
        db.commit()

    send_verification_link(email, request, db)
    return templates.TemplateResponse("register_done.html", {"request": request, "email": email})

# ---------------- Verify via link (magic or verify) ----------------
@app.get("/auth/verify-link")
def auth_verify_link(token: str = Query(...), db: Session = Depends(get_db)):
    session_token = verify_magic_or_verify_link(token, db)
    return {"token": session_token, "message": "Verification successful"}

# ---------------- Login (SSR) ----------------
@app.get("/auth/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/auth/login", response_class=HTMLResponse)
def auth_login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials."}, status_code=401)
    if not user.verified:
        return templates.TemplateResponse("verify_required.html", {"request": request}, status_code=403)

    session_token = generate_token({"email": email, "purpose": "session"})
    return templates.TemplateResponse("verify_success.html", {"request": request, "message": f"Login successful. Token: {session_token}"})

# ---------------- Magic/Verify link (API) ----------------
@app.post("/auth/request-link")
def auth_request_link(payload: Dict[str, str] = Body(...), request: Request = None, db: Session = Depends(get_db)):
    email = (payload.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email required")
    send_verification_link(email, request, db)
    return {"message": "Magic/Verification link sent. If SMTP is not configured, check server logs for the DEV link."}

# ---------------- Protected PDF (Registered-only) ----------------
@app.post("/api/report/pdf")
def report_pdf_api(req: Dict[str, str], user: User = Depends(require_user), db: Session = Depends(get_db)):
    url = req.get("url")
    if not url or not is_valid_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL")

    eng = AuditEngine(url)
    metrics = eng.compute_metrics()

    audit = Audit(user_id=user.id, url=url, metrics_json=json.dumps(metrics),
                  score=metrics[1]["value"], grade=metrics[2]["value"])
    db.add(audit); db.commit()

    pdf = build_pdf_report(audit, metrics)
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="FFTech_Audit.pdf"'},
    )

# ---------------- Schedule (Registered-only) ----------------
@app.post("/api/schedule/set")
def schedule_set(payload: Dict[str, str] = Body(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    """
    payload: { "url": "...", "frequency": "weekly"|"daily", "run_at": "2025-12-29T09:00:00Z" }
    """
    url = (payload.get("url") or "").strip()
    frequency = (payload.get("frequency") or "weekly").strip().lower()
    run_at_iso = payload.get("run_at")
    if not is_valid_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL")
    try:
        run_at = datetime.datetime.fromisoformat(run_at_iso.replace("Z", "+00:00")) if run_at_iso else (now_utc() + datetime.timedelta(days=7))
    except Exception:
        run_at = now_utc() + datetime.timedelta(days=7)
    sch = db.query(Schedule).filter(Schedule.user_id == user.id, Schedule.url == url).first()
    if not sch:
        sch = Schedule(user_id=user.id, url=url, frequency=frequency, enabled=True, next_run_at=run_at)
        db.add(sch)
    else:
        sch.frequency = frequency; sch.enabled = True; sch.next_run_at = run_at
    db.commit()
    return {"message": "Schedule saved", "next_run_at": sch.next_run_at.isoformat()}

# ---------------- Simple background scheduler ----------------
def scheduler_loop():
    while True:
        try:
            db = SessionLocal()
            now = now_utc()
            due = db.query(Schedule).filter(Schedule.enabled == True, Schedule.next_run_at <= now).all()
            for sch in due:
                user = db.query(User).filter(User.id == sch.user_id).first()
                if not user or not user.verified:
                    continue
                eng = AuditEngine(sch.url)
                metrics = eng.compute_metrics()
                audit = Audit(user_id=user.id, url=sch.url, metrics_json=json.dumps(metrics),
                              score=metrics[1]["value"], grade=metrics[2]["value"])
                db.add(audit); db.commit()
                pdf = build_pdf_report(audit, metrics)
                send_email_with_pdf(
                    user.email,
                    subject="Your FF Tech Audit Report",
                    body=f"Attached: 5-page audit report for {sch.url}.",
                    pdf_bytes=pdf,
                    filename="FFTech_Audit.pdf"
                )
                if sch.frequency == "daily":
                    sch.next_run_at = now + datetime.timedelta(days=1)
                else:
                    sch.next_run_at = now + datetime.timedelta(days=7)
                db.commit()
            db.close()
        except Exception as e:
            print(f"[Scheduler] Error: {e}")
        time.sleep(SCHEDULER_SLEEP)

@app.on_event("startup")
def start_scheduler():
    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()
