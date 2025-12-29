
# fftech_audit/app.py
import os, json, traceback, io, datetime, threading, time, logging
from typing import Dict, Any, List
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Form, HTTPException, Body
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .audit_engine import AuditEngine, METRIC_DESCRIPTORS, canonical_origin, aggregate_score, grade_from_score
from .db import SessionLocal, Base, engine, User, Audit, Schedule
from .auth_email import (
    send_verification_link,
    verify_magic_or_verify_link,
    verify_session_token,
    generate_token,
    send_email_with_pdf,
)
from .ui_and_pdf import build_pdf_report
from .db_migration import migrate_schedules_table  # ✅ migration helper

# ------------------------------------------------------------
# Flags & Logging
# ------------------------------------------------------------
ENABLE_AUTH = (os.getenv("ENABLE_AUTH", "true").lower() == "true")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fftech")

# ------------------------------------------------------------
# FastAPI app & middleware
# ------------------------------------------------------------
app = FastAPI(title="FF Tech AI Website Audit SaaS", version="7.3")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ------------------------------------------------------------
# Static
# ------------------------------------------------------------
ROOT_STATIC = os.path.join(os.path.dirname(__file__), "..", "static")
PKG_STATIC = os.path.join(os.path.dirname(__file__), "static")
STATIC_DIR = ROOT_STATIC if os.path.isdir(ROOT_STATIC) else PKG_STATIC
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ------------------------------------------------------------
# SAFE DB INIT → defer to startup (do NOT run at import time)
# ------------------------------------------------------------
def init_db():
    """
    Try to connect and create tables. If DB is misconfigured or down,
    log the error and continue—service must start so Railway healthcheck passes.
    Also run a small migration to add new scheduling columns if missing.
    """
    try:
        with engine.connect() as _:
            pass
        # Create tables (idempotent)
        Base.metadata.create_all(bind=engine)
        # 🔧 Migrate schedules table to add missing columns, safely
        migrate_schedules_table(engine)
        logger.info("DB initialization complete ✅")
    except Exception as e:
        logger.error("DB initialization failed: %s", e)
        logger.error("Service will still start. Check DATABASE_URL later.")

# ------------------------------------------------------------
# Healthcheck → always 200 OK
# ------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.datetime.utcnow().isoformat()}

# ------------------------------------------------------------
# ---------- Open Access ----------
# ------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse("base.html", {"request": request})

@app.post("/audit/open", response_class=HTMLResponse)
def audit_open_ssr(request: Request, url: str = Form(...)):
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return templates.TemplateResponse("base.html", {"request": request, "error": "Invalid URL"}, status_code=400)

    origin = canonical_origin(url)
    try:
        eng = AuditEngine(origin)
        metrics = eng.compute_metrics()
    except Exception as e:
        logger.error("[AUDIT OPEN] Failed: %s", e)
        traceback.print_exc()
        return templates.TemplateResponse("base.html", {"request": request, "error": f"Audit failed: {e}"}, status_code=500)

    security_checks = {
        "https_enabled": metrics.get(10, {}).get("value", True),
        "csp": metrics.get(11, {}).get("value", False),
        "hsts": metrics.get(12, {}).get("value", False),
        "x_frame": metrics.get(13, {}).get("value", False),
        "referrer_policy": metrics.get(14, {}).get("value", False),
    }
    perf = {
        "ttfb_ms": metrics.get(20, {}).get("value", 0),
        "payload_kb": metrics.get(21, {}).get("value", 0),
        "cache_max_age_s": metrics.get(22, {}).get("value", 0),
    }
    seo = {
        "has_title": metrics.get(30, {}).get("value", False),
        "has_meta_desc": metrics.get(31, {}).get("value", False),
        "has_sitemap": metrics.get(32, {}).get("value", False),
        "has_robots": metrics.get(33, {}).get("value", False),
        "structured_data_ok": metrics.get(34, {}).get("value", False),
    }
    mobile = {
        "viewport_ok": metrics.get(40, {}).get("value", False),
        "responsive_meta": metrics.get(41, {}).get("value", False),
    }
    content = {
        "has_h1": metrics.get(50, {}).get("value", False),
        "alt_ok": metrics.get(51, {}).get("value", False),
    }

    overall, category_scores = aggregate_score(
        {"security": security_checks, "performance": perf, "seo": seo, "mobile": mobile, "content": content}
    )
    errors_count = int(metrics.get(100, {}).get("value", 0))
    warnings_count = int(metrics.get(101, {}).get("value", 0))
    notices_count = int(metrics.get(102, {}).get("value", 0))

    overall = max(0.0, overall - min(10, errors_count * 2 + warnings_count * 1))
    grade = grade_from_score(overall)

    strengths = metrics.get(4, {}).get("value", [])
    weaknesses = metrics.get(5, {}).get("value", [])
    priority_fixes = metrics.get(6, {}).get("value", [])

    # Build rows 1..200
    rows = []
    for pid in range(1, 201):
        desc = METRIC_DESCRIPTORS.get(pid, {"name": f"Metric {pid}", "category": "-"})
        cell = metrics.get(pid, {"value": "N/A"})
        val = cell["value"]
        if isinstance(val, (dict, list)):
            try:
                val = json.dumps(val, ensure_ascii=False)
            except Exception:
                val = str(val)
        rows.append({"id": pid, "name": desc["name"], "category": desc["category"], "value": val})

    ctx = {
        "request": request,
        "url_display": origin,
        "score": overall,
        "grade": grade,
        "errors_count": errors_count,
        "warnings_count": warnings_count,
        "notices_count": notices_count,
        "category_scores": category_scores,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "priority_fixes": priority_fixes,
        "rows": rows,
    }
    return templates.TemplateResponse("results.html", ctx)

# ------------------------------------------------------------
# ---------- Registration & Verification ----------
# ------------------------------------------------------------
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
            user = User(name=name.strip() or "User", email=email, plan="free", is_verified=False)
            db.add(user)
            db.commit()
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
        user.is_verified = True
        db.commit()
        session_token = generate_token({"email": email, "purpose": "session"})
        return templates.TemplateResponse(
            "verify_success.html", {"request": request, "message": "Verification successful.", "token": session_token}
        )
    finally:
        db.close()

# ------------------------------------------------------------
# Helper: compute next run in UTC for given local time
# ------------------------------------------------------------
def compute_next_run(
    hour: int, minute: int, tz_name: str, frequency: str, now_utc: datetime.datetime | None = None
) -> datetime.datetime:
    if now_utc is None:
        now_utc = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    now_local = now_utc.astimezone(tz)
    target_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target_local <= now_local:
        target_local += datetime.timedelta(days=1 if frequency == "daily" else 7)
    return target_local.astimezone(datetime.timezone.utc)

# ------------------------------------------------------------
# ---------- Registered Audit & PDF ----------
# ------------------------------------------------------------
@app.post("/audit/user")
def audit_user(req: Dict[str, str] = Body(...)):
    token = (req.get("token") or "").strip()
    url = (req.get("url") or "").strip()
    data = verify_session_token(token)
    email = data.get("email")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user or not user.is_verified:
            raise HTTPException(status_code=403, detail="Email not verified")
        if (user.plan or "free").lower() == "free" and (user.audits_count or 0) >= 10:
            raise HTTPException(status_code=403, detail="Free plan limit reached (10 audits)")
        origin = canonical_origin(url)
        eng = AuditEngine(origin)
        metrics = eng.compute_metrics()

        security_checks = {
            "https_enabled": metrics.get(10, {}).get("value", True),
            "csp": metrics.get(11, {}).get("value", False),
            "hsts": metrics.get(12, {}).get("value", False),
            "x_frame": metrics.get(13, {}).get("value", False),
            "referrer_policy": metrics.get(14, {}).get("value", False),
        }
        perf = {
            "ttfb_ms": metrics.get(20, {}).get("value", 0),
            "payload_kb": metrics.get(21, {}).get("value", 0),
            "cache_max_age_s": metrics.get(22, {}).get("value", 0),
        }
        seo = {
            "has_title": metrics.get(30, {}).get("value", False),
            "has_meta_desc": metrics.get(31, {}).get("value", False),
            "has_sitemap": metrics.get(32, {}).get("value", False),
            "has_robots": metrics.get(33, {}).get("value", False),
            "structured_data_ok": metrics.get(34, {}).get("value", False),
        }
        mobile = {"viewport_ok": metrics.get(40, {}).get("value", False), "responsive_meta": metrics.get(41, {}).get("value", False)}
        content = {"has_h1": metrics.get(50, {}).get("value", False), "alt_ok": metrics.get(51, {}).get("value", False)}

        overall, category_scores = aggregate_score(
            {"security": security_checks, "performance": perf, "seo": seo, "mobile": mobile, "content": content}
        )
        errors_count = int(metrics.get(100, {}).get("value", 0))
        warnings_count = int(metrics.get(101, {}).get("value", 0))
        overall = max(0.0, overall - min(10, errors_count * 2 + warnings_count * 1))
        grade = grade_from_score(overall)

        audit = Audit(user_id=user.id, url=origin, metrics_json=json.dumps(metrics), score=int(round(overall)), grade=grade)
        db.add(audit)
        user.audits_count = (user.audits_count or 0) + 1
        db.commit()

        strengths = metrics.get(4, {}).get("value", [])
        weaknesses = metrics.get(5, {}).get("value", [])
        priority_fixes = metrics.get(6, {}).get("value", [])

        pdf_bytes = build_pdf_report(audit, category_scores, strengths, weaknesses, priority_fixes)
        send_email_with_pdf(user.email, "Your FF Tech Audit Report", "Attached is your 5-page audit report.", pdf_bytes)

        return {"message": "Audit stored", "score": overall, "grade": grade, "audit_id": audit.id}
    finally:
        db.close()

@app.post("/api/report/pdf")
def report_pdf_api(req: Dict[str, str] = Body(...)):
    token = (req.get("token") or "").strip()
    email = verify_session_token(token).get("email")
    url = (req.get("url") or "").strip()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user or not user.is_verified:
            raise HTTPException(status_code=403, detail="Email not verified")
        origin = canonical_origin(url)
        eng = AuditEngine(origin)
        metrics = eng.compute_metrics()

        security_checks = {
            "https_enabled": metrics.get(10, {}).get("value", True),
            "csp": metrics.get(11, {}).get("value", False),
            "hsts": metrics.get(12, {}).get("value", False),
            "x_frame": metrics.get(13, {}).get("value", False),
            "referrer_policy": metrics.get(14, {}).get("value", False),
        }
        perf = {
            "ttfb_ms": metrics.get(20, {}).get("value", 0),
            "payload_kb": metrics.get(21, {}).get("value", 0),
            "cache_max_age_s": metrics.get(22, {}).get("value", 0),
        }
        seo = {
            "has_title": metrics.get(30, {}).get("value", False),
            "has_meta_desc": metrics.get(31, {}).get("value", False),
            "has_sitemap": metrics.get(32, {}).get("value", False),
            "has_robots": metrics.get(33, {}).get("value", False),
            "structured_data_ok": metrics.get(34, {}).get("value", False),
        }
        mobile = {"viewport_ok": metrics.get(40, {}).get("value", False), "responsive_meta": metrics.get(41, {}).get("value", False)}
        content = {"has_h1": metrics.get(50, {}).get("value", False), "alt_ok": metrics.get(51, {}).get("value", False)}

        overall, category_scores = aggregate_score(
            {"security": security_checks, "performance": perf, "seo": seo, "mobile": mobile, "content": content}
        )
        grade = grade_from_score(overall)

        audit = Audit(user_id=user.id, url=origin, metrics_json=json.dumps(metrics), score=int(round(overall)), grade=grade)
        db.add(audit)
        db.commit()

        strengths = metrics.get(4, {}).get("value", [])
        weaknesses = metrics.get(5, {}).get("value", [])
        priority_fixes = metrics.get(6, {}).get("value", [])
        pdf_bytes = build_pdf_report(audit, category_scores, strengths, weaknesses, priority_fixes)

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="FFTech_Audit.pdf"'},
        )
    finally:
        db.close()

# ------------------------------------------------------------
# ---------- Theme toggle & Logout ----------
# ------------------------------------------------------------
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

# ------------------------------------------------------------
# ---------- Scheduling API ----------
# ------------------------------------------------------------
@app.post("/schedule/set")
def schedule_set(req: Dict[str, str] = Body(...)):
    token = (req.get("token") or "").strip()
    url = (req.get("url") or "").strip()
    frequency = (req.get("frequency") or "daily").lower()
    time_of_day = (req.get("time_of_day") or "09:00").strip()
    timezone = (req.get("timezone") or "Asia/Karachi").strip()

    if frequency not in {"daily", "weekly"}:
        raise HTTPException(status_code=400, detail="frequency must be 'daily' or 'weekly'")

    try:
        hh, mm = [int(x) for x in time_of_day.split(":")]
        assert 0 <= hh <= 23 and 0 <= mm <= 59
    except Exception:
        raise HTTPException(status_code=400, detail="time_of_day must be 'HH:MM'")

    email = verify_session_token(token).get("email")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user or not user.is_verified:
            raise HTTPException(status_code=403, detail="Email not verified")
        origin = canonical_origin(url)
        next_run = compute_next_run(hh, mm, timezone, frequency)
        sch = db.query(Schedule).filter(Schedule.user_id == user.id, Schedule.url == origin).first()
        if not sch:
            sch = Schedule(
                user_id=user.id,
                url=origin,
                frequency=frequency,
                enabled=True,
                scheduled_hour=hh,
                scheduled_minute=mm,
                timezone=timezone,
                next_run_at=next_run,
            )
            db.add(sch)
        else:
            sch.frequency = frequency
            sch.enabled = True
            sch.scheduled_hour = hh
            sch.scheduled_minute = mm
            sch.timezone = timezone
            sch.next_run_at = next_run
        db.commit()
        return {
            "message": "Schedule set",
            "schedule_id": sch.id,
            "next_run_at_utc": sch.next_run_at.isoformat(),
            "url": origin,
            "frequency": sch.frequency,
            "time_of_day": f"{hh:02d}:{mm:02d}",
            "timezone": sch.timezone,
        }
    finally:
        db.close()

@app.get("/schedule/list")
def schedule_list(token: str):
    email = verify_session_token(token).get("email")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user or not user.is_verified:
            raise HTTPException(status_code=403, detail="Email not verified")
        items = db.query(Schedule).filter(Schedule.user_id == user.id).all()
        out = []
        for s in items:
            out.append(
                {
                    "schedule_id": s.id,
                    "url": s.url,
                    "enabled": s.enabled,
                    "frequency": s.frequency,
                    "time_of_day": f"{s.scheduled_hour:02d}:{s.scheduled_minute:02d}",
                    "timezone": s.timezone,
                    "next_run_at_utc": s.next_run_at.isoformat() if s.next_run_at else None,
                }
            )
        return {"schedules": out}
    finally:
        db.close()

@app.post("/schedule/disable")
def schedule_disable(req: Dict[str, str] = Body(...)):
    token = (req.get("token") or "").strip()
    schedule_id = int(req.get("schedule_id") or "0")
    email = verify_session_token(token).get("email")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user or not user.is_verified:
            raise HTTPException(status_code=403, detail="Email not verified")
        sch = db.query(Schedule).filter(Schedule.id == schedule_id, Schedule.user_id == user.id).first()
        if not sch:
            raise HTTPException(status_code=404, detail="Schedule not found")
        sch.enabled = False
        db.commit()
        return {"message": "Schedule disabled", "schedule_id": schedule_id}
    finally:
        db.close()

# ------------------------------------------------------------
# ---------- Scheduling loop ----------
# ------------------------------------------------------------
def scheduler_loop():
    while True:
        try:
            db = SessionLocal()
            now_utc = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
            due = db.query(Schedule).filter(Schedule.enabled == True, Schedule.next_run_at <= now_utc).all()
            for sch in due:
                user = db.query(User).filter(User.id == sch.user_id).first()
                if not user or not user.is_verified:
                    continue
                origin = sch.url
                eng = AuditEngine(origin)
                metrics = eng.compute_metrics()

                security_checks = {
                    "https_enabled": metrics.get(10, {}).get("value", True),
                    "csp": metrics.get(11, {}).get("value", False),
                    "hsts": metrics.get(12, {}).get("value", False),
                    "x_frame": metrics.get(13, {}).get("value", False),
                    "referrer_policy": metrics.get(14, {}).get("value", False),
                }
                perf = {
                    "ttfb_ms": metrics.get(20, {}).get("value", 0),
                    "payload_kb": metrics.get(21, {}).get("value", 0),
                    "cache_max_age_s": metrics.get(22, {}).get("value", 0),
                }
                seo = {
                    "has_title": metrics.get(30, {}).get("value", False),
                    "has_meta_desc": metrics.get(31, {}).get("value", False),
                    "has_sitemap": metrics.get(32, {}).get("value", False),
                    "has_robots": metrics.get(33, {}).get("value", False),
                    "structured_data_ok": metrics.get(34, {}).get("value", False),
                }
                mobile = {"viewport_ok": metrics.get(40, {}).get("value", False), "responsive_meta": metrics.get(41, {}).get("value", False)}
                content = {"has_h1": metrics.get(50, {}).get("value", False), "alt_ok": metrics.get(51, {}).get("value", False)}

                overall, category_scores = aggregate_score(
                    {"security": security_checks, "performance": perf, "seo": seo, "mobile": mobile, "content": content}
                )
                grade = grade_from_score(overall)

                audit = Audit(user_id=user.id, url=origin, metrics_json=json.dumps(metrics), score=int(round(overall)), grade=grade)
                db.add(audit)
                db.commit()

                strengths = metrics.get(4, {}).get("value", [])
                weaknesses = metrics.get(5, {}).get("value", [])
                priority_fixes = metrics.get(6, {}).get("value", [])
                pdf_bytes = build_pdf_report(audit, category_scores, strengths, weaknesses, priority_fixes)
                send_email_with_pdf(user.email, "Scheduled FF Tech Audit Report", "Your scheduled audit report is attached.", pdf_bytes)

                sch.next_run_at = compute_next_run(
                    sch.scheduled_hour or 9,
                    sch.scheduled_minute or 0,
                    sch.timezone or "UTC",
                    sch.frequency or "weekly",
                    now_utc=now_utc + datetime.timedelta(seconds=1),
                )
                db.commit()
            db.close()
        except Exception as e:
            logger.error("[Scheduler] Error: %s", e)
        time.sleep(int(os.getenv("SCHEDULER_INTERVAL", "60")))

# ------------------------------------------------------------
# Startup: init DB and start scheduler
# ------------------------------------------------------------
@app.on_event("startup")
def on_startup():
    logger.info("FF Tech Audit SaaS starting up…")
    init_db()
    threading.Thread(target=scheduler_loop, daemon=True).start()
    logger.info("Scheduler started ✅")
