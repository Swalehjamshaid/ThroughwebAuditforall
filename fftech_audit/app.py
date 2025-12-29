
# fftech_audit/app.py
import os
import json
import traceback
from typing import Dict, Any, List

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .audit_engine import AuditEngine, METRIC_DESCRIPTORS, now_utc, is_valid_url

app = FastAPI(title="FF Tech AI Website Audit", version="4.0", description="SSR + API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Global error handler (friendly message + stack logs)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print("[ERROR]", repr(exc))
    traceback.print_exc()
    return PlainTextResponse("Something went wrong rendering the page.\nCheck logs for details.", status_code=500)

# Static mount (serves /static/app.css and /static/app.js)
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Templates
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Health
@app.get("/health")
def health():
    return {"status": "ok", "service": "FF Tech AI Website Audit", "time": now_utc().isoformat()}

# Landing (two options)
@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "build_marker": "v2025-12-28-SSR-Phase1"})

# Open Audit (SSR) — Run Audit button posts here
@app.post("/audit/open", response_class=HTMLResponse)
async def audit_open_ssr(request: Request, url: str = Form(...)):
    url = (url or "").strip()
    if not is_valid_url(url):
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": "Invalid URL. Include http:// or https://", "prefill_url": url, "build_marker": "v2025-12-28-SSR-Phase1"},
            status_code=400,
        )

    try:
        eng = AuditEngine(url)
        metrics: Dict[int, Dict[str, Any]] = eng.compute_metrics()
    except Exception as e:
        print("[AUDIT] Failed for URL:", url, "Error:", repr(e))
        traceback.print_exc()
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": f"Audit failed: {e}", "prefill_url": url, "build_marker": "v2025-12-28-SSR-Phase1"},
            status_code=500,
        )

    # Extract essentials from metrics (IDs aligned with audit_engine.py)
    score          = metrics[1]["value"]
    grade          = metrics[2]["value"]
    summary        = metrics[3]["value"]
    strengths      = metrics[4]["value"]         # list[str]
    weaknesses     = metrics[5]["value"]         # list[str]
    priority_fixes = metrics[6]["value"]         # list[str]
    severity       = metrics[7]["value"]         # dict: {errors, warnings, notices}
    category       = metrics[8]["value"]         # dict: {"Crawlability":..,"On-Page SEO":..,"Performance":..,"Security":..,"Mobile":..}

    # Build rows for the table (stringify complex values)
    rows: List[Dict[str, Any]] = []
    for pid in range(1, 201):
        desc = METRIC_DESCRIPTORS.get(pid, {"name": f"Metric {pid}", "category": "-"})
        cell = metrics.get(pid, {"value": "N/A", "detail": ""})
        val  = cell["value"]
        if isinstance(val, (dict, list)):
            try:
                val = json.dumps(val, ensure_ascii=False)
            except Exception:
                val = str(val)
        rows.append({
            "id": pid, "name": desc["name"], "category": desc["category"],
            "value": val, "detail": cell.get("detail", "")
        })

    ctx = {
        "request": request,
        "build_marker": "v2025-12-28-SSR-Phase1",
        "url": url,
        "score": score,
        "grade": grade,
        "summary": summary,
        "severity": severity,
        "category_scores": category,               # ✅ Jinja block reads this
        "category_json": json.dumps(category),     # ✅ Chart.js reads this
        "strengths": strengths,                    # ✅ Jinja list
        "weaknesses": weaknesses,                  # ✅ Jinja list
        "priority_fixes": priority_fixes,          # ✅ Jinja list
        "rows": rows,
        "allow_pdf": False
    }
    return templates.TemplateResponse("results.html", ctx)
