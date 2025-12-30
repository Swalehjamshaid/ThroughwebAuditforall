
# fftech_audit/app.py
from fastapi import FastAPI, Request, Form, HTTPException, Body
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
import os
import datetime
import logging

from fftech_audit.audit_engine import run_audit

log = logging.getLogger("uvicorn.error")

app = FastAPI()

# Templates directory (fixed in your project)
templates = Jinja2Templates(directory="fftech_audit/templates")

# ---------- SAFE STATIC MOUNT ----------
static_dir = Path(os.getenv("STATIC_DIR", "fftech_audit/static")).resolve()
try:
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    print(f"[startup] Mounted static at '/static' -> {static_dir}")
except Exception as e:
    print(f"[startup][warn] Could not mount static directory '{static_dir}': {e}")

# ---------- MODELS ----------
class AuditRequest(BaseModel):
    url: str

# ---------- ROUTES ----------
@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("landing.html", {
        "request": request,
        "now": datetime.datetime.utcnow()
    })

@app.post("/audit/open", response_class=HTMLResponse)
async def audit_open(
    request: Request,
    url: str | None = Form(default=None),
    json_body: dict | None = Body(default=None),
):
    """
    Accept BOTH form and JSON for convenience.
    Render results.html with top-level variables expected by your fixed template:
    - metrics
    - category_breakdown
    - charts
    """
    try:
        target_url = (url or (json_body.get("url") if json_body else None) or "").strip()
        if not target_url:
            raise HTTPException(status_code=400, detail="Missing URL")

        audit = run_audit(target_url)
        metrics = audit.get("metrics", {})
        category_breakdown = audit.get("category_breakdown", {})
        charts = audit.get("charts", {})

        # Log some context to help future triage
        log.info(f"[audit] Completed for {metrics.get('target.url')} with overall {metrics.get('overall.health_score')}")

        return templates.TemplateResponse("results.html", {
            "request": request,
            "now": datetime.datetime.utcnow(),
            # Provide both nested and top-level keys so either template style works
            "audit": audit,
            "metrics": metrics,
            "category_breakdown": category_breakdown,
            "charts": charts,
        })

    except HTTPException:
        raise
    except Exception as e:
        log.exception(f"[audit_open] Rendering failed: {e}")
        # Return a simple HTML error so users don't see raw JSON detail
        return HTMLResponse(
            content=f"<h3>Audit failed</h3><p>{str(e)}</p>",
            status_code=400
        )

@app.post("/audit/api")
async def audit_api(req: AuditRequest):
    try:
        return run_audit(req.url.strip())
    except Exception as e:
        log.exception(f"[audit_api] {e}")
        raise HTTPException(status_code=400, detail=f"Audit failed: {e}")

@app.get("/register", response_class=HTMLResponse)
async def register(request: Request):
    return templates.TemplateResponse("register.html", {
        "request": request,
        "now": datetime.datetime.utcnow()
    })

@app.get("/register_done", response_class=HTMLResponse)
async def register_done(request: Request, email: str):
    return templates.TemplateResponse("register_done.html", {
        "request": request,
        "email": email,
        "now": datetime.datetime.utcnow()
    })

@app.get("/schedule", response_class=HTMLResponse)
async def schedule(request: Request):
    return templates.TemplateResponse("schedule.html", {
        "request": request,
        "now": datetime.datetime.utcnow()
    })

@app.post("/schedule/set")
async def schedule_set(payload: dict):
    # Stub: integrate with scheduler/DB; UI expects JSON with "next_run_at_utc"
    return {"status": "ok", "next_run_at_utc": "2025-01-01T09:00:00Z"}

@app.get("/verify_success", response_class=HTMLResponse)
async def verify_success(request: Request, verified: bool = True):
    return templates.TemplateResponse("verify_success.html", {
        "request": request,
        "verified": verified,
        "now": datetime.datetime.utcnow()
    })

@app.get("/health")
async def health():
    return {"status": "ok"}
