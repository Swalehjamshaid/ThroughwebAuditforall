
# fftech_audit/app.py
import os, json, traceback, io, datetime, threading, time, logging
from typing import Dict, Any, List

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Form, HTTPException, Body
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .audit_engine import AuditEngine, METRIC_DESCRIPTORS, grade_from_score
# If you use DB features, keep these imports and safe init. Otherwise you can comment them.
from .db import SessionLocal, Base, engine, User, Audit, Schedule
from .auth_email import send_verification_link, verify_magic_or_verify_link, verify_session_token, generate_token, send_email_with_pdf
from .ui_and_pdf import build_pdf_report
from .db_migration import migrate_schedules_table

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fftech")

app = FastAPI(title="FF Tech AI Website Audit SaaS", version="7.4")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ROOT_STATIC = os.path.join(os.path.dirname(__file__), "..", "static")
PKG_STATIC  = os.path.join(os.path.dirname(__file__), "static")
STATIC_DIR  = ROOT_STATIC if os.path.isdir(ROOT_STATIC) else PKG_STATIC
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

def init_db():
    try:
        with engine.connect() as _:
            pass
        Base.metadata.create_all(bind=engine)
        migrate_schedules_table(engine)
        logger.info("DB initialization complete ✅")
    except Exception as e:
        logger.error("DB initialization failed: %s", e)

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.datetime.utcnow().isoformat()}

@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@app.post("/audit/open", response_class=HTMLResponse)
def audit_open_ssr(request: Request, url: str = Form(...)):
    url = (url or "").strip()
    logger.info("[/audit/open] URL=%s", url)
    if not url.lower().startswith(("http://", "https://")):
        return templates.TemplateResponse("home.html", {"request": request, "error": "Invalid URL (must start with http:// or https://)"}, status_code=400)
    target = url

    try:
        eng = AuditEngine(target)
        metrics = eng.compute_metrics()
        logger.info("[/audit/open] Metrics OK (%d keys)", len(metrics))
    except Exception as e:
        logger.error("[/audit/open] Failed: %s", e)
        traceback.print_exc()
        return templates.TemplateResponse("home.html", {"request": request, "error": f"Audit failed: {e}"}, status_code=500)

    # Read required display fields from metrics
    score = float(metrics.get(1, {}).get("value", 0.0))
    grade = metrics.get(2, {}).get("value", grade_from_score(score))

    # Build 200 rows exactly in order
    rows: List[Dict[str, Any]] = []
    for mid in range(1, 201):
        desc = METRIC_DESCRIPTORS.get(mid, {"name": f"Metric {mid}", "category": "-"})
        val  = metrics.get(mid, {"value": "N/A"})["value"]
        if isinstance(val, (dict, list)):
            try:
                val = json.dumps(val, ensure_ascii=False)
            except Exception:
                val = str(val)
        rows.append({"id": mid, "name": desc["name"], "category": desc["category"], "value": val})

    ctx = {
        "request": request,
        "url_display": target,
        "score": score,
        "grade": grade,
        "rows": rows,
    }
    return templates.TemplateResponse("results.html", ctx)

# ----------------------------
# Registration & verification
# ----------------------------
@app.get("/auth/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/auth/register", response_class=HTMLResponse)
def auth_register(request: Request, email: str = Form(...), name: str = Form("User")):
    email = (email or "").strip().lower()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(name=name.strip() or "User", email=email, plan='free', is_verified=False)
            db.add(user); db.commit()
        send_verification_link(email)
        return templates.TemplateResponse("register_done.html", {"request": request, "email": email})
    finally:
        db.close()

@app.get("/auth/verify-link", response_class=HTMLResponse)
def auth_verify_link(request: Request, token: str):
    email = verify_magic_or_verify_link(token)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.is_verified = True; db.commit()
        session_token = generate_token({"email": email, "purpose": "session"})
        return templates.TemplateResponse("verify_success.html", {"request": request, "message": "Verification successful.", "token": session_token})
    finally:
        db.close()

# ----------------------------
# Theme + logout
# ----------------------------
@app.post("/theme/toggle")
def toggle_theme(request: Request):
    current = request.cookies.get("theme", "dark")
    new_theme = "light" if current == "dark" else "dark"
    resp = JSONResponse({"ok": True, "theme": new_theme})
    resp.set_cookie("theme", new_theme, max_age=60 * 60 * 24 * 180, samesite="lax")
    return resp

@app.post("/auth/logout")
@app.post("/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("token")
    return resp

# ----------------------------
# Startup
# ----------------------------
@app.on_event("startup")
def on_startup():
    logger.info("FF Tech Audit SaaS starting up…")
    init_db()
    logger.info("Startup complete ✅")
