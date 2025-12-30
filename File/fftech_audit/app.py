
# fftech_audit/app.py
import os
import uuid
import datetime as dt
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Request, Form
from fastapi import BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from audit_engine import run_audit
from ui_and_pdf import build_rows_for_ui, make_pdf_bytes
from auth_email import send_magic_link_email, verify_token
from db import SessionLocal, get_user_by_email, upsert_user, save_schedule, compute_next_run_utc
from db import AuditHistory, create_audit_history
from sqlalchemy.orm import Session

# --- App & templates ---
app = FastAPI(title="FF Tech AI • Website Audit")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Static files (CSS/JS/images that you add later)
static_dir = os.path.join(BASE_DIR, "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


def _now_utc():
    return dt.datetime.utcnow()


# ----- Landing / Home -----
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Render clean landing page
    return templates.TemplateResponse(
        "landing.html",
        {
            "request": request,
            "now": _now_utc(),
        },
    )


# ----- Open Audit -----
@app.post("/audit/open", response_class=HTMLResponse)
async def audit_open(request: Request, url: str = Form(...)):
    """
    Accepts a URL, runs the audit engine, and renders results.
    """
    # Run audit (deterministic stub + extensible)
    metrics = run_audit(url)

    # Produce UI rows for "Key Signals"
    rows = build_rows_for_ui(metrics)

    # Save a lightweight history (optional)
    with SessionLocal() as db:
        create_audit_history(db, url=url, health_score=float(metrics.get("overall.health_score") or 0.0))

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "now": _now_utc(),
            "url": url,
            "metrics": metrics,
            "rows": rows,
        },
    )


# ----- Export PDF -----
@app.post("/audit/pdf")
async def audit_pdf(url: str = Form(...)):
    """
    Regenerate audit (or you can accept submitted metrics) and return a 5-page PDF.
    """
    metrics = run_audit(url)
    rows = build_rows_for_ui(metrics)

    pdf_bytes = make_pdf_bytes(url=url, metrics=metrics, rows=rows)

    filename = f"fftech_audit_{uuid.uuid4().hex[:8]}.pdf"
    pdf_path = os.path.join(BASE_DIR, filename)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    # Return as file; you may switch to StreamingResponse
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"FFTechAI_{url.replace('https://', '').replace('http://', '').replace('/', '_')}.pdf",
    )


# ----- Register -----
@app.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {
            "request": request,
            "now": _now_utc(),
        },
    )


@app.post("/register", response_class=HTMLResponse)
async def register_post(
    request: Request,
    background: BackgroundTasks,
    email: str = Form(...),
):
    """
    Send passwordless magic link to the email (stubbed sender).
    """
    with SessionLocal() as db:
        user = get_user_by_email(db, email)
        if not user:
            user = upsert_user(db, email=email)

    # Create a signed token (stub) and send email
    token = verify_token.issue(email)  # token string
    background.add_task(send_magic_link_email, email=email, token=token)

    return templates.TemplateResponse(
        "register_done.html",
        {
            "request": request,
            "now": _now_utc(),
            "email": email,
        },
    )


# ----- Verify -----
@app.get("/verify", response_class=HTMLResponse)
async def verify(request: Request, token: str):
    """
    Verify token; if ok → set session cookie (omitted) or mark verified in UI.
    """
    ok, email = verify_token.check(token)
    # If you implement sessions, set a secure cookie here.

    return templates.TemplateResponse(
        "verify_success.html",
        {
            "request": request,
            "now": _now_utc(),
            "verified": ok,
            "email": email if ok else None,
        },
    )


# ----- Schedule -----
@app.get("/schedule", response_class=HTMLResponse)
async def schedule(request: Request):
    return templates.TemplateResponse(
        "schedule.html",
        {
            "request": request,
            "now": _now_utc(),
        },
    )


@app.post("/schedule/set")
async def schedule_set(payload: Dict[str, Any]):
    """
    Save schedule definition and return next run time (UTC).
    payload: {url, frequency, time_of_day, timezone}
    """
    url = (payload.get("url") or "").strip()
    frequency = (payload.get("frequency") or "weekly").strip().lower()
    time_of_day = (payload.get("time_of_day") or "09:00").strip()
    timezone = (payload.get("timezone") or "UTC").strip()

    if not url:
        return JSONResponse(status_code=400, content={"detail": "URL is required"})

    # Save to DB
    with SessionLocal() as db:
        save_schedule(db, url=url, frequency=frequency, time_of_day=time_of_day, timezone=timezone)

    next_run_at_utc = compute_next_run_utc(frequency=frequency, time_of_day=time_of_day)

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "next_run_at_utc": next_run_at_utc.isoformat(timespec="minutes") + "Z",
        },
    )


# ----- Optional: Index of results when no metrics -----
@app.get("/audit/results", response_class=HTMLResponse)
async def results_empty(request: Request):
    """
    Render results page with empty state (no metrics yet).
    """
    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "now": _now_utc(),
            "url": None,
            "metrics": {"overall.health_score": None},  # trigger empty state block
            "rows": [],
        },
    )
