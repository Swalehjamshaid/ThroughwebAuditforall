
# fftech_audit/app.py
import os
import uuid
import datetime as dt
from typing import Dict, Any

from fastapi import FastAPI, Request, Form, BackgroundTasks, Body
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from fftech_audit.audit_engine import run_audit
from fftech_audit.ui_and_pdf import build_rows_for_ui, make_pdf_bytes
from fftech_audit.auth_email import send_magic_link_email, verify_token
from fftech_audit.db import (
    SessionLocal,
    get_user_by_email,
    upsert_user,
    save_schedule,
    compute_next_run_utc,
    create_audit_history,
    count_user_audits,
)

app = FastAPI(title="FF Tech AI • Website Audit")

# Cookie session for passwordless login
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "change-me-secret"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Static mount (logo, assets)
static_dir = os.path.join(BASE_DIR, "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


def _now_utc():
    return dt.datetime.utcnow()


# ------------------ Pages ------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request, "now": _now_utc()})


@app.get("/audit/results", response_class=HTMLResponse)
async def results_empty(request: Request):
    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "now": _now_utc(),
            "url": None,
            "metrics": {"overall.health_score": None},  # trigger empty state
            "rows": [],
        },
    )


@app.post("/audit/open", response_class=HTMLResponse)
async def audit_open(request: Request, url: str = Form(...)):
    """
    Open-access and registered audits.
    - Open access: no audit history.
    - Registered: history stored and free plan cap enforced (10 audits).
    """
    user_id = request.session.get("user_id")
    plan = request.session.get("plan", "free")

    # Enforce free plan limit
    if user_id:
        with SessionLocal() as db:
            cnt = count_user_audits(db, user_id)
            if plan == "free" and cnt >= 10:
                return templates.TemplateResponse(
                    "results.html",
                    {
                        "request": request,
                        "now": _now_utc(),
                        "url": url,
                        "metrics": {"overall.health_score": None},
                        "rows": [],
                        "limit_message": "Free plan limit reached (10 audits). Upgrade to enable more audits and scheduling.",
                    },
                )

    # Run audit (includes crawl + analyzers + numbered metrics + scoring)
    audit = run_audit(url)

    # UI rows for cards
    rows = build_rows_for_ui(audit["metrics"], audit["category_breakdown"])

    # Save history only for registered users
    if user_id:
        with SessionLocal() as db:
            create_audit_history(db, url=url, health_score=float(audit["metrics"].get("overall.health_score") or 0.0), user_id=user_id)

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "now": _now_utc(),
            "url": url,
            "metrics": audit["metrics"],
            "rows": rows,
        },
    )


@app.post("/audit/pdf")
async def audit_pdf(url: str = Form(...)):
    audit = run_audit(url)
    rows = build_rows_for_ui(audit["metrics"], audit["category_breakdown"])
    pdf_bytes = make_pdf_bytes(url=url, metrics=audit["metrics"], rows=rows, charts=audit.get("charts", {}))

    filename = f"fftech_audit_{uuid.uuid4().hex[:8]}.pdf"
    pdf_path = os.path.join(BASE_DIR, filename)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    safe_name = url.replace("https://", "").replace("http://", "").replace("/", "_")
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"FFTechAI_{safe_name}.pdf")


@app.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "now": _now_utc()})


@app.post("/register", response_class=HTMLResponse)
async def register_post(request: Request, background: BackgroundTasks, email: str = Form(...)):
    with SessionLocal() as db:
        user = get_user_by_email(db, email)
        if not user:
            user = upsert_user(db, email=email)
    token = verify_token.issue(email)  # 15 min TTL
    background.add_task(send_magic_link_email, email=email, token=token)
    return templates.TemplateResponse("register_done.html", {"request": request, "now": _now_utc(), "email": email})


@app.get("/verify", response_class=HTMLResponse)
async def verify(request: Request, token: str):
    ok, email = verify_token.check(token)
    if ok:
        with SessionLocal() as db:
            user = get_user_by_email(db, email)
        request.session["user_id"] = user.id
        request.session["email"] = user.email
        request.session["plan"] = user.plan  # free / subscriber
    return templates.TemplateResponse(
        "verify_success.html",
        {"request": request, "now": _now_utc(), "verified": ok, "email": email if ok else None},
    )


@app.get("/schedule", response_class=HTMLResponse)
async def schedule(request: Request):
    return templates.TemplateResponse("schedule.html", {"request": request, "now": _now_utc()})


@app.post("/schedule/set")
async def schedule_set(request: Request, payload: Dict[str, Any] = Body(...)):
    """
    Save schedule; only allowed for logged-in subscribers.
    """
    user_id = request.session.get("user_id")
    plan = request.session.get("plan", "free")
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Login required"})
    if plan != "subscriber":
        return JSONResponse(status_code=403, content={"detail": "Subscription required for scheduling"})

    url = (payload.get("url") or "").strip()
    frequency = (payload.get("frequency") or "weekly").strip().lower()
    time_of_day = (payload.get("time_of_day") or "09:00").strip()
    timezone = (payload.get("timezone") or "UTC").strip()

    if not url:
        return JSONResponse(status_code=400, content={"detail": "URL is required"})

    with SessionLocal() as db:
        save_schedule(db, user_id=user_id, url=url, frequency=frequency, time_of_day=time_of_day, timezone=timezone)

    next_run_at_utc = compute_next_run_utc(frequency=frequency, time_of_day=time_of_day)
    return JSONResponse(status_code=200, content={"ok": True, "next_run_at_utc": next_run_at_utc.isoformat(timespec="minutes") + "Z"})


# ------------------ JSON APIs ------------------

@app.post("/api/audit", response_class=JSONResponse)
async def api_audit(payload: Dict[str, Any] = Body(...)):
    url = (payload.get("url") or "").strip()
    if not url:
        return JSONResponse(status_code=400, content={"detail": "URL is required"})
    audit = run_audit(url)
    rows = [{"label": r.label, "value": r.value} for r in build_rows_for_ui(audit["metrics"], audit["category_breakdown"])]
    return JSONResponse(content={"url": url, "metrics": audit["metrics"], "rows": rows, "category_breakdown": audit["category_breakdown"]})


@app.post("/api/audit/pdf", response_class=JSONResponse)
async def api_audit_pdf(payload: Dict[str, Any] = Body(...)):
    url = (payload.get("url") or "").strip()
    if not url:
        return JSONResponse(status_code=400, content={"detail": "URL is required"})
    audit = run_audit(url)
    rows = build_rows_for_ui(audit["metrics"], audit["category_breakdown"])
    pdf_bytes = make_pdf_bytes(url=url, metrics=audit["metrics"], rows=rows, charts=audit.get("charts", {}))
    return JSONResponse(content={"ok": True, "pdf_size_bytes": len(pdf_bytes)})
