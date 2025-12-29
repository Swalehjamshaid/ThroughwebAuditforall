
# fftech_audit/app.py
import os, io, json, datetime, threading, time
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

from .settings import settings
from .db import ( SessionLocal, get_db, Base, engine, User, Audit, Schedule,
                  ensure_schedule_columns, ensure_user_columns )
from .auth_email import ( send_verification_link, verify_magic_or_verify_link,
                          verify_session_token, hash_password, verify_password,
                          send_email_with_pdf, generate_token )
from .audit_engine import AuditEngine, METRIC_DESCRIPTORS, now_utc, is_valid_url
from .ui_and_pdf import build_pdf_report

# App init
app = FastAPI(title="FF Tech AI Website Audit", version="4.0", description="SSR + API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
security = HTTPBearer()

# Static mount & availability check
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
STATIC_OK = os.path.isdir(STATIC_DIR) and \
            os.path.isfile(os.path.join(STATIC_DIR, "app.css")) and \
            os.path.isfile(os.path.join(STATIC_DIR, "app.js"))
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Templates
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# DB init
Base.metadata.create_all(bind=engine)
try:
    ensure_schedule_columns()
    ensure_user_columns()
except Exception as e:
    print(f"[Startup] ensure_* failed: {e}")

def assets() -> Dict[str, str]:
    use_cdn = settings.USE_CDN_ASSETS or not STATIC_OK
    return {
        "font_href": settings.GOOGLE_FONT_CSS,
        "css_href": ("/static/app.css" if not use_cdn else "https://unpkg.com/modern-css-reset/dist/reset.min.css"),
        "chartjs_src": settings.CHARTJS_CDN,
        "js_src": ("/static/app.js" if not use_cdn else "https://unpkg.com/placeholder-js@1.0.0/index.js"),
    }

def ctx_base(request: Request) -> Dict[str, Any]:
    return {"request": request, "ASSETS": assets(), "build_marker": "v2025-12-28-SSR-8"}

# Health
@app.get("/health")
def health():
    return {"status": "ok", "service": "FF Tech AI Website Audit", "time": now_utc().isoformat()}

# Landing
@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse("index.html", ctx_base(request))

# Open Audit (SSR)
@app.post("/audit/open", response_class=HTMLResponse)
async def audit_open_ssr(request: Request, url: str = Form(...)):
    if not is_valid_url(url):
        ctx = ctx_base(request); ctx.update({"error": "Invalid URL", "prefill_url": url})
        return templates.TemplateResponse("index.html", ctx, status_code=400)

    try:
        eng = AuditEngine(url)
        metrics = eng.compute_metrics()
    except Exception as e:
        ctx = ctx_base(request); ctx.update({"error": f"Audit failed: {e}", "prefill_url": url})
        return templates.TemplateResponse("index.html", ctx, status_code=500)

    score = metrics[1]["value"]; grade = metrics[2]["value"]
    summary = metrics[3]["value"]; category = metrics[8]["value"]; severity = metrics[7]["value"]

    rows: List[Dict[str, Any]] = []
    for pid in range(1, 201):
        desc = METRIC_DESCRIPTORS.get(pid, {"name": "(Unknown)", "category": "-"})
        cell = metrics.get(pid, {"value": "N/A", "detail": ""}); val = cell["value"]
        if isinstance(val, (dict, list)):
            try:
                val = json.dumps(val, ensure_ascii=False)
            except Exception:
                val = str(val)
        rows.append({"id": pid, "name": desc["name"], "category": desc["category"], "value": val, "detail": cell.get("detail", "")})

    ctx = ctx_base(request)
    ctx.update({
        "url": url, "score": score, "grade": grade, "summary": summary,
        "severity": severity, "category": category, "rows": rows,
        "allow_pdf": False,
    })
    return templates.TemplateResponse("results.html", ctx)

# API: open audit JSON
@app.post("/api/audit/open")
def api_audit_open(payload: Dict[str, str] = Body(...)):
    url = payload.get("url")
    if not url or not is_valid_url(url): raise HTTPException(status_code=400, detail="Invalid URL")
    eng = AuditEngine(url); metrics = eng.compute_metrics()
    score = metrics[1]["value"]; grade = metrics[2]["value"]
    db = next(get_db()); audit = Audit(user_id=None, url=url, metrics_json=json.dumps(metrics), score=score, grade=grade)
    db.add(audit); db.commit()
    return {"url": url, "score": score, "grade": grade, "metrics": metrics}

@app.get("/api/metrics/descriptors")
def api_metric_descriptors(): return METRIC_DESCRIPTORS

# Auth helpers
def require_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)) -> User:
    payload = verify_session_token(credentials.credentials)
    email = payload.get("email"); user = db.query(User).filter(User.email == email).first()
    if not user: raise HTTPException(status_code=401, detail="User not found")
    if not user.verified: raise HTTPException(status_code=403, detail="Email not verified")
    return user

# Registration (SSR)
@app.get("/auth/register", response_class=HTMLResponse)
def register_page(request: Request): return templates.TemplateResponse("register.html", ctx_base(request))

@app.post("/auth/register", response_class=HTMLResponse)
def auth_register(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    email = email.strip().lower(); name = name.strip()
    if not (name and email and password):
        ctx = ctx_base(request); ctx["error"] = "Please fill in all fields."
        return templates.TemplateResponse("register.html", ctx, status_code=400)
    user = db.query(User).filter(User.email == email).first()
    if user and user.password_hash:
        ctx = ctx_base(request); ctx["error"] = "Email already registered."
        return templates.TemplateResponse("register.html", ctx, status_code=400)
    if not user:
        user = User(name=name, email=email, password_hash=hash_password(password), verified=False, plan="free")
        db.add(user); db.commit()
    else:
        user.name = name; user.password_hash = hash_password(password); user.verified = False; db.commit()
    send_verification_link(email, request, db)
    return templates.TemplateResponse("register_done.html", ctx_base(request) | {"email": email})

# Verify via link
@app.get("/auth/verify-link")
def auth_verify_link(token: str = Query(...), db: Session = Depends(get_db)):
    session_token = verify_magic_or_verify_link(token, db)
    return {"token": session_token, "message": "Verification successful"}

# Login (SSR)
@app.get("/auth/login", response_class=HTMLResponse)
def login_page(request: Request): return templates.TemplateResponse("login.html", ctx_base(request))

@app.post("/auth/login", response_class=HTMLResponse)
def auth_login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    email = email.strip().lower(); user = db.query(User).filter(User.email == email).first()
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        ctx = ctx_base(request); ctx["error"] = "Invalid credentials."
        return templates.TemplateResponse("login.html", ctx, status_code=401)
    if not user.verified: return templates.TemplateResponse("verify_required.html", ctx_base(request), status_code=403)
    session_token = generate_token({"email": email, "purpose": "session"})
    return templates.TemplateResponse("verify_success.html", ctx_base(request) | {"message": f"Login successful. Token: {session_token}"})

# Protected PDF (Registered-only)
@app.post("/api/report/pdf")
def report_pdf_api(req: Dict[str, str], user: User = Depends(require_user), db: Session = Depends(get_db)):
    url = req.get("url")
    if not url or not is_valid_url(url): raise HTTPException(status_code=400, detail="Invalid URL")
    eng = AuditEngine(url); metrics = eng.compute_metrics()
    audit = Audit(user_id=user.id, url=url, metrics_json=json.dumps(metrics), score=metrics[1]["value"], grade=metrics[2]["value"])
    db.add(audit); db.commit()
    pdf = build_pdf_report(audit, metrics)
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="FFTech_Audit.pdf"'}
    )

# Schedule (Registered-only)
@app.post("/api/schedule/set")
def schedule_set(payload: Dict[str, str] = Body(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    url = (payload.get("url") or "").strip()
    freq = (payload.get("frequency") or "weekly").strip().lower()
    run_at_iso = payload.get("run_at")
    if not is_valid_url(url): raise HTTPException(status_code=400, detail="Invalid URL")
    try:
        run_at = datetime.datetime.fromisoformat(run_at_iso.replace("Z", "+00:00")) if run_at_iso else (now_utc() + datetime.timedelta(days=7))
    except Exception:
        run_at = now_utc() + datetime.timedelta(days=7)
    sch = db.query(Schedule).filter(Schedule.user_id == user.id, Schedule.url == url).first()
    if not sch:
        sch = Schedule(user_id=user.id, url=url, frequency=freq, enabled=True, next_run_at=run_at); db.add(sch)
    else:
        sch.frequency = freq; sch.enabled = True; sch.next_run_at = run_at
    db.commit(); return {"message": "Schedule saved", "next_run_at": sch.next_run_at.isoformat()}

# Background scheduler
def scheduler_loop():
    while True:
        try:
            db = SessionLocal(); now = now_utc()
            due = db.query(Schedule).filter(Schedule.enabled == True, Schedule.next_run_at <= now).all()
            for sch in due:
                user = db.query(User).filter(User.id == sch.user_id).first()
                if not user or not user.verified: continue
                eng = AuditEngine(sch.url); metrics = eng.compute_metrics()
                audit = Audit(user_id=user.id, url=sch.url, metrics_json=json.dumps(metrics),
                              score=metrics[1]["value"], grade=metrics[2]["value"])
                db.add(audit); db.commit()
                pdf = build_pdf_report(audit, metrics)
                send_email_with_pdf(user.email, "Your FF Tech Audit Report",
                                    f"Attached: 5-page audit report for {sch.url}.", pdf, "FFTech_Audit.pdf")
                sch.next_run_at = now + (datetime.timedelta(days=1) if sch.frequency == "daily" else datetime.timedelta(days=7))
                db.commit()
            db.close()
        except Exception as e:
            print(f"[Scheduler] Error: {e}")
        time.sleep(settings.SCHEDULER_INTERVAL)

@app.on_event("startup")
def start_scheduler():
    threading.Thread(target=scheduler_loop, daemon=True).start()
