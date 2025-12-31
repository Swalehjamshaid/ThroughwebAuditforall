
# fftech_audit/app.py (v2.2 — safer defaults + rows & competitors exposed)
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
    url: str | None = None

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
    Defaults to Haier Pakistan if URL is missing/blank.
    """
    try:
        target_url = (url or (json_body.get("url") if json_body else None) or "").strip() or "https://www.haier.com.pk"

        audit = run_audit(target_url)
        metrics = audit.get("metrics", {})
        category_breakdown = audit.get("category_breakdown", {})
        charts = audit.get("charts", {})
        competitors = audit.get("competitors", [])

        log.info(f"[audit] Completed for {metrics.get('target.url')} overall {metrics.get('overall.health_score')} ({metrics.get('overall.grade')})")

        return templates.TemplateResponse("results.html", {
            "request": request,
            "now": datetime.datetime.utcnow(),
            "audit": audit,
            "metrics": metrics,
            "category_breakdown": category_breakdown,
            "charts": charts,
            "rows": metrics.get("rows", []),          # ensure non-empty rows for Key Signals
            "competitors": competitors,               # exposed in case you add to template later
        })

    except HTTPException:
        raise
    except Exception as e:
        log.exception(f"[audit_open] Rendering failed: {e}")
        return HTMLResponse(
            content=f"<h3>Audit failed</h3><p>{str(e)}</p>",
            status_code=400
        )

@app.post("/audit/api")
async def audit_api(req: AuditRequest):
    try:
        target = (req.url or "").strip() or "https://www.haier.com.pk"
        return run_audit(target)
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

# --- Direct runner (reads PORT and starts Uvicorn) ---
if __name__ == "__main__":
    import os
    import uvicorn

    # Railway injects PORT; fallback to 8080 for local runs
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("fftech_audit.app:app", host="0.0.0.0", port=port)
