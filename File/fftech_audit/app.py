# fftech_audit/app.py
from __future__ import annotations
import logging
from typing import Any, Dict, Optional
from datetime import datetime

from fastapi import FastAPI, Request, Form, BackgroundTasks, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

# ---- Import from audit_engine.py ----
from .audit_engine import AuditEngine, generate_pdf_report

# ---- Optional modules (safe fallbacks) ----
send_verification_email = None
verify_token = None
try:
    from .auth_email import send_verification_email as _send_verif, verify_token as _verify_tok
    send_verification_email = _send_verif
    verify_token = _verify_tok
except Exception:
    pass

db_create_user = None
db_get_user_by_email = None
db_save_audit = None
try:
    from .db import create_user as _create_user, get_user_by_email as _get_user, save_audit as _save_audit
    db_create_user = _create_user
    db_get_user_by_email = _get_user
    db_save_audit = _save_audit
except Exception:
    pass

# ---- Logging ----
logger = logging.getLogger("fftech")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# ---- FastAPI App ----
app = FastAPI(
    title="FF Tech AI Website Audit",
    description="Professional AI-powered SEO audit with instant reports and PDF exports.",
    version="1.0.0"
)

# ---- CORS (restrict in production) ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change to your domain(s) in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Static Files (CSS, JS, images) ----
app.mount("/static", StaticFiles(directory="fftech_audit/static"), name="static")

# ---- Templates ----
templates = Jinja2Templates(directory="fftech_audit/templates")
templates.env.globals.update({
    "len": len,
    "now": datetime.utcnow()
})

# ---- Audit Engine Instance ----
engine = AuditEngine()

# ---- Utility Functions ----
def base_ctx(request: Request, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ctx = {
        "request": request,
        "now": datetime.utcnow()
    }
    if extra:
        ctx.update(extra)
    return ctx

def _normalize_url(raw: str) -> str:
    url = (raw or "").strip().lower()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url

def _render_results(request: Request, raw_url: Optional[str]) -> Any:
    url = _normalize_url(raw_url or "")

    # Empty state – show welcome screen
    if not url:
        metrics = engine.run("")  # Returns welcome metrics with None scores
        rows = metrics.get("rows", [])
        return templates.TemplateResponse(
            "results.html",
            base_ctx(request, {"url": None, "metrics": metrics, "rows": rows})
        )

    # Real audit
    try:
        logger.info("Auditing %s", url)
        metrics = engine.run(url)
    except Exception as e:
        logger.exception("Audit failed for %s", url)
        raise HTTPException(status_code=500, detail="Unable to analyze this website. Please try again later.")

    rows = metrics.get("rows", [])

    # Optional: save to DB
    if db_save_audit:
        try:
            db_save_audit(url=url, metrics=metrics)
        except Exception as db_e:
            logger.warning("Failed to save audit: %s", db_e)

    return templates.TemplateResponse(
        "results.html",
        base_ctx(request, {"url": url, "metrics": metrics, "rows": rows})
    )

# ---------------------------
# ROUTES
# ---------------------------

@app.get("/", include_in_schema=False)
async def landing(request: Request):
    """Landing / Home page"""
    return templates.TemplateResponse("landing.html", base_ctx(request))

@app.get("/audit/open")
async def audit_open_get(request: Request, url: Optional[str] = Query(None)):
    """Direct access with ?url= or show form"""
    return _render_results(request, url)

@app.post("/audit/open")
async def audit_open_post(request: Request, url: str = Form(...)):
    """Form submission – run audit"""
    return _render_results(request, url)

@app.get("/register")
async def register_get(request: Request):
    return templates.TemplateResponse("register.html", base_ctx(request))

@app.post("/register")
async def register_post(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...)
):
    email = email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")

    if db_create_user and db_get_user_by_email:
        try:
            if not db_get_user_by_email(email):
                db_create_user(email=email)
        except Exception as e:
            logger.warning("DB user creation failed: %s", e)

    if send_verification_email:
        try:
            background_tasks.add_task(send_verification_email, email)
        except Exception as e:
            logger.warning("Failed to send email: %s", e)

    return templates.TemplateResponse("register_done.html", base_ctx(request, {"email": email}))

# Alias routes
@app.get("/auth/register")
async def auth_register_get(request: Request):
    return await register_get(request)

@app.post("/auth/register")
async def auth_register_post(request: Request, background_tasks: BackgroundTasks, email: str = Form(...)):
    return await register_post(request, background_tasks, email)

@app.get("/verify-success")
@app.get("/auth/verify-success")
async def verify_success(
    request: Request,
    token: Optional[str] = Query(None),
    email: Optional[str] = Query(None)
):
    verified = False
    if verify_token and token and email:
        try:
            verified = bool(verify_token(email=email, token=token))
        except Exception as e:
            logger.warning("Token verification failed: %s", e)
    return templates.TemplateResponse(
        "verify_success.html",
        base_ctx(request, {"verified": verified, "email": email})
    )

@app.get("/schedule")
async def schedule_get(request: Request):
    return templates.TemplateResponse("schedule.html", base_ctx(request))

# ---------------------------
# JSON API
# ---------------------------
@app.post("/api/audit")
async def api_audit(url: str = Form(...)):
    norm = _normalize_url(url)
    if not norm:
        raise HTTPException(status_code=400, detail="URL is required")
    try:
        metrics = engine.run(norm)
        return JSONResponse(content=metrics)
    except Exception as e:
        logger.exception("API audit failed: %s", e)
        raise HTTPException(status_code=500, detail="Audit failed")

# ---------------------------
# PDF Export
# ---------------------------
@app.post("/audit/pdf")
async def audit_pdf(url: str = Form(...)):
    norm = _normalize_url(url)
    if not norm:
        raise HTTPException(status_code=400, detail="URL required for PDF")

    metrics = engine.run(norm)

    if not generate_pdf_report:
        raise HTTPException(status_code=501, detail="PDF generation not available")

    pdf_bytes = generate_pdf_report(url=norm, metrics=metrics)

    domain = norm.replace("https://", "").replace("http://", "").split("/")[0]
    filename = f"FFTech_AI_Audit_{domain}_{datetime.utcnow().strftime('%Y%m%d')}.pdf"

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

# ---------------------------
# Health Check
# ---------------------------
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "FF Tech AI Website Audit",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
