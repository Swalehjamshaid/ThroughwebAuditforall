
# fftech_audit/app.py
import os, json, traceback, datetime, logging
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# --- Your audit engine (must exist) ---
from .audit_engine import AuditEngine, METRIC_DESCRIPTORS, grade_from_score

# ----------------------------------------------------------------------
# Flags & Logging
# ----------------------------------------------------------------------
ENABLE_AUTH = (os.getenv("ENABLE_AUTH", "true").lower() == "true")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fftech")

# ----------------------------------------------------------------------
# FastAPI app & middleware
# ----------------------------------------------------------------------
app = FastAPI(title="FF Tech AI • Website Audit SaaS", version="8.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------------
# Static files
# ----------------------------------------------------------------------
ROOT_STATIC = os.path.join(os.path.dirname(__file__), "..", "static")
PKG_STATIC  = os.path.join(os.path.dirname(__file__), "static")
STATIC_DIR  = ROOT_STATIC if os.path.isdir(ROOT_STATIC) else PKG_STATIC
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ----------------------------------------------------------------------
# Templates
# ----------------------------------------------------------------------
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

def _pick_landing_template() -> str:
    """
    Autodetect the landing template based on common filenames.
    This makes app.py 'connect' to whichever file you actually use.
    """
    candidates = [
        "audit.html",          # very likely your file (based on screenshot)
        "index.html",
        "landing.html",
        "home.html",
        "main.html",
    ]
    for name in candidates:
        path = os.path.join(TEMPLATES_DIR, name)
        if os.path.isfile(path):
            logger.info("[landing] Using template: %s", name)
            return name
    # Fallback if none found
    logger.warning("[landing] No known landing template found; defaulting to home.html")
    return "home.html"

LANDING_TEMPLATE = _pick_landing_template()

# ----------------------------------------------------------------------
# Healthcheck (Railway)
# ----------------------------------------------------------------------
@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "time": datetime.datetime.utcnow().isoformat()}

# ----------------------------------------------------------------------
# Landing → render your detected landing HTML
# ----------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def landing(request: Request) -> HTMLResponse:
    """
    Renders your landing file (audit/index/landing/home), and passes ENABLE_AUTH
    so base/header can show 'Register' when enabled.
    """
    return templates.TemplateResponse(LANDING_TEMPLATE, {
        "request": request,
        "ENABLE_AUTH": ENABLE_AUTH,
    })

# Optional helper: the 'New Audit' button could point here
@app.get("/new")
def new_audit() -> RedirectResponse:
    return RedirectResponse(url="/")

# ----------------------------------------------------------------------
# Audit endpoint (FORM → POST /audit/open)
# ----------------------------------------------------------------------
@app.post("/audit/open", response_class=HTMLResponse)
def audit_open(request: Request, url: str = Form(...)) -> HTMLResponse:
    """
    Receives <input name="url"> from your landing form. 
    Runs the audit and renders results.html with score/grade + 200 metrics.
    """
    url = (url or "").trim() if hasattr(str, "trim") else (url or "").strip()
    logger.info("[/audit/open] URL=%s", url)

    if not url.lower().startswith(("http://", "https://")):
        return templates.TemplateResponse(LANDING_TEMPLATE, {
            "request": request,
            "ENABLE_AUTH": ENABLE_AUTH,
            "error": "Invalid URL (must start with http:// or https://)"
        }, status_code=400)

    try:
        eng = AuditEngine(url)           # ✅ audit the EXACT URL typed (full path)
        metrics = eng.compute_metrics()
        logger.info("[/audit/open] Metrics OK (%d keys)", len(metrics))
    except Exception as e:
        logger.error("[/audit/open] Audit failed: %s", e)
        traceback.print_exc()
        return templates.TemplateResponse(LANDING_TEMPLATE, {
            "request": request,
            "ENABLE_AUTH": ENABLE_AUTH,
            "error": f"Audit failed: {e}"
        }, status_code=500)

    return _render_results(request, url, metrics)

# ----------------------------------------------------------------------
# Audit endpoint (JS → GET /analyze?url=...)
# ----------------------------------------------------------------------
@app.get("/analyze", response_class=HTMLResponse)
def analyze(request: Request, url: Optional[str] = Query(None)) -> HTMLResponse:
    """
    Use this if your 'Analyze Now' button triggers JS instead of a form submit.
    Example: window.location = `/analyze?url=${encodeURIComponent(inputValue)}`
    """
    if not url:
        return templates.TemplateResponse(LANDING_TEMPLATE, {
            "request": request,
            "ENABLE_AUTH": ENABLE_AUTH,
            "error": "Please provide a ?url= parameter"
        }, status_code=400)

    url = url.strip()
    logger.info("[/analyze] URL=%s", url)

    if not url.lower().startswith(("http://", "https://")):
        return templates.TemplateResponse(LANDING_TEMPLATE, {
            "request": request,
            "ENABLE_AUTH": ENABLE_AUTH,
            "error": "Invalid URL (must start with http:// or https://)"
        }, status_code=400)

    try:
        eng = AuditEngine(url)
        metrics = eng.compute_metrics()
        logger.info("[/analyze] Metrics OK (%d keys)", len(metrics))
    except Exception as e:
        logger.error("[/analyze] Audit failed: %s", e)
        traceback.print_exc()
        return templates.TemplateResponse(LANDING_TEMPLATE, {
            "request": request,
            "ENABLE_AUTH": ENABLE_AUTH,
            "error": f"Audit failed: {e}"
        }, status_code=500)

    return _render_results(request, url, metrics)

# ----------------------------------------------------------------------
# Results page rendering
# ----------------------------------------------------------------------
def _render_results(request: Request, target_url: str, metrics: Dict[int, Dict[str, Any]]) -> HTMLResponse:
    """
    Common renderer for the results, used by both POST /audit/open and GET /analyze.
    Expects a 'results.html' template that extends your base.html.
    """
    # #1 Overall Site Health Score (%)  | #2 Grade (A+ to D)
    score = float(metrics.get(1, {}).get("value", 0.0))
    grade = metrics.get(2, {}).get("value", grade_from_score(score))

    # #8 Category Score Breakdown (optional chart)
    category_breakdown = metrics.get(8, {}).get("value", {})

    # Build 1..200 rows for the metrics table
    rows: List[Dict[str, Any]] = []
    for mid in range(1, 201):
        desc = METRIC_DESCRIPTORS.get(mid, {"name": f"Metric {mid}", "category": "-"})
        cell = metrics.get(mid, {"value": "N/A"})
        val  = cell["value"]
        if isinstance(val, (dict, list)):
            try:
                val = json.dumps(val, ensure_ascii=False)
            except Exception:
                val = str(val)
        rows.append({
            "id": mid,
            "name": desc["name"],
            "category": desc["category"],
            "value": val
        })

    return templates.TemplateResponse("results.html", {
        "request": request,
        "ENABLE_AUTH": ENABLE_AUTH,
        "url_display": target_url,
        "score": score,
        "grade": grade,
        "category_breakdown": category_breakdown,
        "rows": rows
    })

# ----------------------------------------------------------------------
# Optional: theme toggle (if you add a button for it)
# ----------------------------------------------------------------------
@app.post("/theme/toggle")
def toggle_theme(request: Request):
    current = request.cookies.get("theme", "dark")
    new_theme = "light" if current == "dark" else "dark"
    resp = JSONResponse({"ok": True, "theme": new_theme})
    resp.set_cookie("theme", new_theme, max_age=60 * 60 * 24 * 180, samesite="lax")
    return resp
