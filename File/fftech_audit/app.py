
# fftech_audit/app.py
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import datetime

from fftech_audit.audit_engine import run_audit

app = FastAPI()
templates = Jinja2Templates(directory="fftech_audit/templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

class AuditRequest(BaseModel):
    url: str

@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request, "now": datetime.datetime.utcnow()})

# Form submit from landing page
@app.post("/audit/open", response_class=HTMLResponse)
async def audit_open(request: Request, url: str = Form(...)):
    try:
        audit = run_audit(url)
        # results.html should render using "audit" dict (metrics/category_breakdown/charts)
        return templates.TemplateResponse("results.html", {
            "request": request,
            "audit": audit,
            "now": datetime.datetime.utcnow()
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Audit failed: {e}")

# JSON API (optional for programmatic calls)
@app.post("/audit/api")
async def audit_api(req: AuditRequest):
    try:
        return run_audit(req.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Audit failed: {e}")

@app.get("/register", response_class=HTMLResponse)
async def register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "now": datetime.datetime.utcnow()})

@app.get("/register_done", response_class=HTMLResponse)
async def register_done(request: Request, email: str):
    return templates.TemplateResponse("register_done.html", {"request": request, "email": email, "now": datetime.datetime.utcnow()})

@app.get("/schedule", response_class=HTMLResponse)
async def schedule(request: Request):
    return templates.TemplateResponse("schedule.html", {"request": request, "now": datetime.datetime.utcnow()})

@app.post("/schedule/set")
async def schedule_set(payload: dict):
    # Stub: wire to a DB/scheduler if needed. Returns a success message for UI.
    return {"status": "ok", "next_run_at_utc": "2025-01-01T09:00:00Z"}

@app.get("/verify_success", response_class=HTMLResponse)
async def verify_success(request: Request, verified: bool = True):
    return templates.TemplateResponse("verify_success.html", {"request": request, "verified": verified, "now": datetime.datetime.utcnow()})

@app.get("/health")
async def health():
    return {"status": "ok"}
