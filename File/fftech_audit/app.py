# fftech_audit/app.py
import os, json, traceback, io, datetime, time, threading
from typing import Dict, Any, List

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Form, HTTPException, Query, Depends, Body
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .audit_engine import AuditEngine, METRIC_DESCRIPTORS, now_utc, is_valid_url
from .db import ( SessionLocal, get_db, Base, engine, User, Audit, Schedule, MagicLink, EmailCode, ensure_schedule_columns, ensure_user_columns )
from .auth_email import ( send_verification_link, verify_magic_or_verify_link, verify_session_token, hash_password, verify_password, send_email_with_pdf, generate_token )
from .ui_and_pdf import build_pdf_report

ENABLE_AUTH = (os.getenv("ENABLE_AUTH","true").lower() == "true")

app = FastAPI(title="FF Tech AI Website Audit", version="4.0", description="SSR + API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print("[ERROR]", repr(exc)); traceback.print_exc()
    return PlainTextResponse("Something went wrong rendering the page.\nCheck logs for details.", status_code=500)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(STATIC_DIR): app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

Base.metadata.create_all(bind=engine)
try:
    ensure_schedule_columns()
    ensure_user_columns()
except Exception as e:
    print(f"[Startup] ensure_* failed: {e}")

@app.get("/health")
def health(): return {"status": "ok", "service": "FF Tech AI Website Audit", "time": now_utc().isoformat()}

@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "ENABLE_AUTH": ENABLE_AUTH, "build_marker": "v2025-12-28-SSR-Final"})

# Phase 1: Open Audit
@app.post("/audit/open", response_class=HTMLResponse)
async def audit_open_ssr(request: Request, url: str = Form(...)):
    url = (url or "").strip()
    if not is_valid_url(url):
        return templates.TemplateResponse("index.html", {"request": request, "error": "Invalid URL. Include http:// or https://", "prefill_url": url, "ENABLE_AUTH": ENABLE_AUTH, "build_marker": "v2025-12-28-SSR-Final"}, status_code=400)
    try:
        eng = AuditEngine(url); metrics: Dict[int, Dict[str, Any]] = eng.compute_metrics()
    except Exception as e:
        print("[AUDIT] Failed for URL:", url, "Error:", repr(e)); traceback.print_exc()
        return templates.TemplateResponse("index.html", {"request": request, "error": f"Audit failed: {e}", "prefill_url": url, "ENABLE_AUTH": ENABLE_AUTH, "build_marker": "v2025-12-28-SSR-Final"}, status_code=500)

    score          = metrics[1]["value"]; grade = metrics[2]["value"]
    summary        = metrics[3]["value"]; strengths = metrics[4]["value"]; weaknesses = metrics[5]["value"]
    priority_fixes = metrics[6]["value"]; severity  = metrics[7]["value"]; category   = metrics[8]["value"]

    rows: List[Dict[str, Any]] = []
    for pid in range(1, 201):
        desc = METRIC_DESCRIPTORS.get(pid, {"name": f"Metric {pid}", "category": "-"})
        cell = metrics.get(pid, {"value": "N/A", "detail": ""})
        val  = cell["value"]
        if isinstance(val, (dict, list)):
            try: val = json.dumps(val, ensure_ascii=False)
            except Exception: val = str(val)
        rows.append({"id": pid, "name": desc["name"], "category": desc["category"], "value": val, "detail": cell.get("detail","")})

    ctx = {
        "request": request, "ENABLE_AUTH": ENABLE_AUTH, "build_marker":"v2025-12-28-SSR-Final",
        "url": url, "score": score, "grade": grade, "summary": summary, "severity": severity,
        "category_scores": category, "category_json": json.dumps(category),
        "strengths": strengths, "weaknesses": weaknesses, "priority_fixes": priority_fixes,
        "rows": rows, "allow_pdf": False
    }
    return templates.TemplateResponse("results.html", ctx)

# Phase 2: Auth routes

def require_user_token(token: str, db: Session) -> User:
    payload = verify_session_token(token)
    email = payload.get("email")
    user = db.query(User).filter(User.email == email).first()
    if not user: raise HTTPException(status_code=401, detail="User not found")
    if not user.verified: raise HTTPException(status_code=403, detail="Email not verified")
    return user

@app.get("/auth/register", response_class=HTMLResponse)
def register_page(request: Request):
    if not ENABLE_AUTH: return PlainTextResponse("Auth disabled. Set ENABLE_AUTH=true in .env", status_code=404)
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/auth/register", response_class=HTMLResponse)
def auth_register(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if not ENABLE_AUTH: return PlainTextResponse("Auth disabled. Set ENABLE_AUTH=true in .env", status_code=404)
    email = email.strip().lower(); name = name.strip()
    if not (name and email and password):
        return templates.TemplateResponse("register.html", {"request": request, "error": "Please fill in all fields."}, status_code=400)
    user = db.query(User).filter(User.email == email).first()
    if user and user.password_hash:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Email already registered."}, status_code=400)
    if not user:
        user = User(name=name, email=email, password_hash=hash_password(password), verified=False, plan="free")
        db.add(user); db.commit()
    else:
        user.name = name; user.password_hash = hash_password(password); user.verified = False; db.commit()
    send_verification_link(email, request, db)
    return templates.TemplateResponse("register_done.html", {"request": request, "email": email})

@app.get("/auth/login", response_class=HTMLResponse)
def login_page(request: Request):
    if not ENABLE_AUTH: return PlainTextResponse("Auth disabled. Set ENABLE_AUTH=true in .env", status_code=404)
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/auth/login", response_class=HTMLResponse)
def auth_login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if not ENABLE_AUTH: return PlainTextResponse("Auth disabled. Set ENABLE_AUTH=true in .env", status_code=404)
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials."}, status_code=401)
    if not user.verified:
        return templates.TemplateResponse("verify_required.html", {"request": request}, status_code=403)
    session_token = generate_token({"email": email, "purpose": "session"})
    return templates.TemplateResponse("verify_success.html", {"request": request, "message": f"Login successful. Token: {session_token}"})

@app.get("/auth/verify-link")
def auth_verify_link(token: str = Query(...), db: Session = Depends(get_db)):
    if not ENABLE_AUTH: return PlainTextResponse("Auth disabled. Set ENABLE_AUTH=true in .env", status_code=404)
    session_token = verify_magic_or_verify_link(token, db)
    return {"token": session_token, "message": "Verification successful"}

# Registered-only: PDF & Schedule
@app.post("/api/report/pdf")
def report_pdf_api(req: Dict[str, str] = Body(...), db: Session = Depends(get_db)):
    token = (req.get("token") or "").strip()
    user = require_user_token(token, db)
    url = (req.get("url") or "").strip()
    if not is_valid_url(url): raise HTTPException(status_code=400, detail="Invalid URL")
    eng = AuditEngine(url); metrics = eng.compute_metrics()
    audit = Audit(user_id=user.id, url=url, metrics_json=json.dumps(metrics), score=metrics[1]["value"], grade=metrics[2]["value"])
    db.add(audit); db.commit()
    pdf = build_pdf_report(audit, metrics)
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": 'attachment; filename="FFTech_Audit.pdf"'})

@app.post("/api/schedule/set")
def schedule_set(req: Dict[str, str] = Body(...), db: Session = Depends(get_db)):
    token = (req.get("token") or "").strip()
    user = require_user_token(token, db)
    url = (req.get("url") or "").strip()
    frequency = (req.get("frequency") or "weekly").strip().lower()
    run_at_iso = req.get("run_at")
    if not is_valid_url(url): raise HTTPException(status_code=400, detail="Invalid URL")
    try:
        run_at = datetime.datetime.fromisoformat(run_at_iso.replace("Z","+00:00")) if run_at_iso else now_utc() + datetime.timedelta(days=7)
    except Exception:
        run_at = now_utc() + datetime.timedelta(days=7)
    sch = db.query(Schedule).filter(Schedule.user_id == user.id, Schedule.url == url).first()
    if not sch:
        sch = Schedule(user_id=user.id, url=url, frequency=frequency, enabled=True, next_run_at=run_at); db.add(sch)
    else:
        sch.frequency = frequency; sch.enabled = True; sch.next_run_at = run_at
    db.commit(); return {"message":"Schedule saved", "next_run_at": sch.next_run_at.isoformat()}

# Background scheduler (Phase 2 email)

def scheduler_loop():
    while True:
        try:
            db = SessionLocal(); now = now_utc()
            due = db.query(Schedule).filter(Schedule.enabled == True, Schedule.next_run_at <= now).all()
            for sch in due:
                user = db.query(User).filter(User.id == sch.user_id).first()
                if not user or not user.verified: continue
                eng = AuditEngine(sch.url); metrics = eng.compute_metrics()
                audit = Audit(user_id=user.id, url=sch.url, metrics_json=json.dumps(metrics), score=metrics[1]["value"], grade=metrics[2]["value"])
                db.add(audit); db.commit()
                pdf = build_pdf_report(audit, metrics)
                send_email_with_pdf(user.email, "Your FF Tech Audit Report",
                                    f"Attached: 5-page audit report for {sch.url}.", pdf, "FFTech_Audit.pdf")
                sch.next_run_at = now + (datetime.timedelta(days=1) if sch.frequency == "daily" else datetime.timedelta(days=7))
                db.commit()
            db.close()
        except Exception as e:
            print("[Scheduler] Error:", e)
        time.sleep(int(os.getenv("SCHEDULER_INTERVAL","60")))

@app.on_event("startup")
def start_scheduler():
    if ENABLE_AUTH:
        threading.Thread(target=scheduler_loop, daemon=True).start()
