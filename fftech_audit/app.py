
# fftech_audit/app.py
import os, io, json, traceback
from typing import Dict, Any, List

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Request, Form, Body
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .settings import settings
from .db import Base, engine
from .audit_engine import AuditEngine, METRIC_DESCRIPTORS, now_utc, is_valid_url

app = FastAPI(title="FF Tech AI Website Audit", version="4.0", description="SSR + API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Global error handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print("[ERROR]", repr(exc)); traceback.print_exc()
    return PlainTextResponse("Something went wrong rendering the page.\nCheck logs for details.", status_code=500)

# Static mount & existence check
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
STATIC_OK = os.path.isdir(STATIC_DIR) and \
            os.path.isfile(os.path.join(STATIC_DIR, "app.css")) and \
            os.path.isfile(os.path.join(STATIC_DIR, "app.js"))
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Templates
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# DB init
Base.metadata.create_all(bind=engine)

def assets() -> Dict[str, str]:
    use_cdn = settings.USE_CDN_ASSETS or not STATIC_OK
    return {
        "font_href": settings.GOOGLE_FONT_CSS,
        "css_href": ("/static/app.css" if not use_cdn else "https://unpkg.com/modern-css-reset/dist/reset.min.css"),
        "chartjs_src": settings.CHARTJS_CDN,
        "js_src": ("/static/app.js" if not use_cdn else "https://unpkg.com/placeholder-js@1.0.0/index.js"),
    }

def ctx_base(request: Request) -> Dict[str, Any]:
    return {"request": request, "ASSETS": assets(), "build_marker": "v2025-12-28-SSR-Phase1"}

# Health
@app.get("/health")
def health():
    return {"status": "ok", "service": "FF Tech AI Website Audit", "time": now_utc().isoformat()}

# Landing (two options)
@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse("index.html", ctx_base(request))

# Open Audit (SSR)
@app.post("/audit/open", response_class=HTMLResponse)
async def audit_open_ssr(request: Request, url: str = Form(...)):
    if not is_valid_url(url):
        ctx = ctx_base(request); ctx.update({"error": "Invalid URL", "prefill_url": url})
        return templates.TemplateResponse("index.html", ctx, status_code=400)
    try:
        eng = AuditEngine(url)
        metrics = eng.compute_metrics()
    except Exception as e:
        print("[AUDIT] Failed:", url, repr(e)); traceback.print_exc()
        ctx = ctx_base(request); ctx.update({"error": f"Audit failed: {e}", "prefill_url": url})
        return templates.TemplateResponse("index.html", ctx, status_code=500)

    score = metrics[1]["value"]; grade = metrics[2]["value"]
    summary = metrics[3]["value"]; category = metrics[8]["value"]; severity = metrics[7]["value"]

    # JSON stringify complex values for table
    rows: List[Dict[str, Any]] = []
    for pid in range(1, 201):
        desc = METRIC_DESCRIPTORS.get(pid, {"name": "(Unknown)", "category": "-"})
        cell = metrics.get(pid, {"value": "N/A", "detail": ""})
        val = cell["value"]
        if isinstance(val, (dict, list)):
            try: val = json.dumps(val, ensure_ascii=False)
            except Exception: val = str(val)
        rows.append({"id": pid, "name": desc["name"], "category": desc["category"], "value": val, "detail": cell.get("detail", "")})

    # category JSON for charts
    category_json = json.dumps(category, ensure_ascii=False)

    ctx = ctx_base(request)
    ctx.update({
        "url": url, "score": score, "grade": grade, "summary": summary,
        "severity": severity, "category_json": category_json, "rows": rows,
        "allow_pdf": False
    })
    return templates.TemplateResponse("results.html", ctx)

# Optional: descriptor API
@app.get("/api/metrics/descriptors")
def api_metric_descriptors():
    return METRIC_DESCRIPTORS

# Placeholders for Phase 2 (avoid 404 during Phase 1)
@app.get("/auth/login")
def login_placeholder():
    return PlainTextResponse("Auth will be enabled in Phase 2 (set ENABLE_AUTH=true in .env).")
@app.get("/auth/register")
def register_placeholder():
    return PlainTextResponse("Auth will be enabled in Phase 2 (set ENABLE_AUTH=true in .env).")
