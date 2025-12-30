
# fftech_audit/app.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from datetime import datetime

from fastapi import FastAPI, Request, Form, BackgroundTasks, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

# ---- External modules (with safe fallbacks) -------------------------------
try:
    from .audit_engine import AuditEngine
except Exception as e:
    raise RuntimeError(f"Failed to import AuditEngine: {e}")

# PDF generator can exist either in audit_engine or a dedicated ui_and_pdf module.
generate_pdf_report = None
try:
    from .ui_and_pdf import generate_pdf_report as _pdf_gen
    generate_pdf_report = _pdf_gen
except Exception:
    try:
        # Fallback to the one in audit_engine if available
        from .audit_engine import generate_pdf_report as _pdf_gen2
        generate_pdf_report = _pdf_gen2
    except Exception:
        generate_pdf_report = None  # we will guard when using it

# Email (passwordless) helpers
send_verification_email = None
verify_token = None
try:
    from .auth_email import send_verification_email as _send_verif, verify_token as _verify_tok
    send_verification_email = _send_verif
    verify_token = _verify_tok
except Exception:
    # Keep None; routes will no-op or explain feature not configured.
    pass

# DB helpers
db_create_user = None
db_get_user_by_email = None
db_save_audit = None
db_list_audits = None
try:
    from .db import create_user as _create_user, get_user_by_email as _get_user, save_audit as _save_audit, list_audits as _list_audits
    db_create_user = _create_user
    db_get_user_by_email = _get_user
    db_save_audit = _save_audit
    db_list_audits = _list_audits
except Exception:
    # Optional; feature will still work without persistence.
    pass

# ---- Logging --------------------------------------------------------------
logger = logging.getLogger("fftech")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# ---- FastAPI app ----------------------------------------------------------
app = FastAPI(title="FFTech AI Website Audit SaaS")

# ---- CORS (optional; adjust domains for production) -----------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Static files ---------------------------------------------------------
# Serve /static from fftech_audit/static (if the folder exists)
app.mount("/static", StaticFiles(directory="fftech_audit/static"), name="static")

# ---- Jinja templates ------------------------------------------------------
templates = Jinja2Templates(directory="fftech_audit/templates")
# Optional convenience; templates already use Jinja filters like |length
templates.env.globals["len"] = len

# ---- Engine ---------------------------------------------------------------
engine = AuditEngine()

# Utility: common context
def base_ctx(request: Request, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {"request": request, "now": datetime.utcnow()}
    if extra:
        ctx.update(extra)
    return ctx

# ---------------------------
# ROUTES (HTML pages)
# ---------------------------

@app.get("/", include_in_schema=False)
async def landing(request: Request):
    """
    Landing page (200 OK). Extends base.html via landing.html.
    """
    return templates.TemplateResponse("landing.html", base_ctx(request))

@app.get("/register")
async def register_get(request: Request):
    """
    Show registration (email) form.
    """
    return templates.TemplateResponse("register.html", base_ctx(request))

@app.post("/register")
async def register_post(request: Request, background_tasks: BackgroundTasks, email: str = Form(...)):
    """
    Handle email-based registration (passwordless).
    - Optional DB: create user record
    - Optional Email: send verification/magic link
    - Render register_done.html
    """
    email = (email or "").strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Please provide a valid email address.")

    # Persist user (optional)
    if db_get_user_by_email and db_create_user:
        try:
            user = db_get_user_by_email(email)
            if not user:
                db_create_user(email=email)
        except Exception as e:
            logger.warning(f"DB user create/get failed: {e}")

    # Send verification email (optional)
    if send_verification_email:
        try:
            background_tasks.add_task(send_verification_email, email)
        except Exception as e:
            logger.warning(f"Email send failed: {e}")

    return templates.TemplateResponse("register_done.html", base_ctx(request, {"email": email}))

@app.get("/verify-success")
async def verify_success(request: Request, token: Optional[str] = Query(None), email: Optional[str] = Query(None)):
    """
    Email verification success page.
    """
    verified = False
    if verify_token and token and email:
        try:
            verified = bool(verify_token(email=email, token=token))
        except Exception as e:
            logger.warning(f"Token verification failed: {e}")
    return templates.TemplateResponse("verify_success.html", base_ctx(request, {"verified": verified, "email": email}))

@app.get("/schedule")
async def schedule_get(request: Request):
    """
    Scheduling page (for registered users).
    """
    return templates.TemplateResponse("schedule.html", base_ctx(request))

# ---------------------------
# AUDIT: GET (form or run) + POST (run)
# ---------------------------

@app.get("/audit/open")
async def audit_open_get(request: Request, url: Optional[str] = Query(None)):
    """
    GET: Show audit form (results.html) or run audit if ?url= provided.
    """
    if url:
        logger.info("[GET /audit/open] Running audit for %s", url)
        metrics: Dict[str, Any] = engine.run(url)
        rows = metrics.get("rows", [])
        # Optional: save audit to DB
        if db_save_audit:
            try:
                db_save_audit(url=url, metrics=metrics)
            except Exception as e:
                logger.warning(f"Saving audit failed: {e}")
        return templates.TemplateResponse("results.html", base_ctx(request, {"url": url, "metrics": metrics, "rows": rows}))
    # Render empty form
    return templates.TemplateResponse("results.html", base_ctx(request, {"url": None, "metrics": {}, "rows": []}))

@app.post("/audit/open")
async def audit_open_post(request: Request, url: str = Form(...)):
    """
    POST: Executes the audit and renders results.
    """
    url = (url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Please provide a URL to audit.")
    logger.info("[POST /audit/open] Starting audit for %s", url)

    metrics: Dict[str, Any] = engine.run(url)
    rows = metrics.get("rows", [])
    logger.info("[POST /audit/open] Metrics OK (%s keys)", len(metrics))

    # Optional: save audit to DB
    if db_save_audit:
        try:
            db_save_audit(url=url, metrics=metrics)
        except Exception as e:
            logger.warning(f"Saving audit failed: {e}")

    return templates.TemplateResponse("results.html", base_ctx(request, {"url": url, "metrics": metrics, "rows": rows}))

@app.post("/audit/pdf")
async def audit_pdf(url: str = Form(...)) -> StreamingResponse:
    """
    Generate a 5-page, client-ready PDF for the given URL and return it.
    """
    url = (url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required to generate PDF.")
    metrics = engine.run(url)
    rows = metrics.get("rows", [])

    if not generate_pdf_report:
        raise HTTPException(status_code=501, detail="PDF generation is not configured.")

    pdf_bytes = generate_pdf_report(url=url, metrics=metrics, rows=rows)
    filename = f"FFTech_Audit_{url.replace('https://','').replace('http://','').replace('/','_')}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

# ---------------------------
# HEALTH
# ---------------------------

@app.get("/health", include_in_schema=False)
async def health() -> Dict[str, str]:
    """
    Simple health endpoint (200 OK) for platform liveness.
    """
    return {"status": "ok"}
