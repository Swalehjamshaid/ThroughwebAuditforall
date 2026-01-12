
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

from .db import engine, Base
from .routers import health, auth, audits, pages

# Optional reporting/graphics modules
try:
    from . import report  # expected to expose: build_report(graded_df_or_dict, output_dir, formats=["pdf"], **kwargs)
except Exception:
    report = None  # fallback handled later

APP_TITLE = "FF Tech AI Website Audit SaaS"
APP_VERSION = "1.0.0"
TZ_OFFSET = timezone(timedelta(hours=5))  # GMT+05:00

app = FastAPI(title=APP_TITLE, version=APP_VERSION)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
EXPORT_DIR = BASE_DIR / "export"
EXPORT_DIR.mkdir(exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# -----------------------------------------------------------------------------
# Lifecycle
# -----------------------------------------------------------------------------
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


# -----------------------------------------------------------------------------
# Helpers & Domain stubs (replace with real audit logic / DB queries)
# -----------------------------------------------------------------------------

def _now_year() -> int:
    return datetime.now(TZ_OFFSET).year


def grade_to_letter(score: float) -> str:
    if score >= 95:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    return "D"


def run_open_audit(url: str) -> Dict[str, Any]:
    """Quick, stateless audit for Open Access users.
    Replace this stub with your actual crawling, Lighthouse/Core Web Vitals, and SEO checks.
    """
    # Minimal synthetic metrics for UI wiring; back-end should compute real values.
    # NOTE: No persistence for open access.
    overall_score = 82
    metrics = {
        "executive_summary": {
            "overall_site_health_score": overall_score,
            "website_grade": grade_to_letter(overall_score),
            "summary": (
                "This website demonstrates solid technical performance with moderate SEO completeness. "
                "Key strengths include stable HTTPS and mobile-friendly layout. Opportunities remain in "
                "structured data, image optimization, and internal linking hygiene."
            ),
            "strengths": ["HTTPS configured", "Mobile friendly", "Low 5xx errors"],
            "weak_areas": ["Missing structured data", "Large images", "Duplicate headings"],
            "priority_fixes": ["Compress images", "Add schema.org markup", "Consolidate duplicate H1/H2"],
            "category_breakdown": {"Crawlability": 78, "On-Page SEO": 74, "Performance": 80, "Security": 88, "Mobile": 83},
        },
        "overall_site_health": {
            "total_errors": 23,
            "total_warnings": 67,
            "total_notices": 120,
            "total_crawled_pages": 250,
            "total_indexed_pages": 220,
            "issues_trend": [12, 16, 10, 8, 6],
            "crawl_budget_efficiency": 0.86,
            "orphan_pages_pct": 3.2,
            "completion_status": "Complete",
        },
        "url": url,
    }
    return metrics


def build_dashboard_charts() -> Dict[str, Any]:
    return {
        "trend": {"labels": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"], "values": [4, 6, 3, 8, 7, 9]},
        "severity": {"labels": ["Critical", "High", "Medium", "Low"], "values": [5, 12, 20, 8]},
        "top_owners": {"labels": ["Ops", "IT", "Finance", "HR"], "values": [22, 18, 12, 9]},
    }


def build_audit_detail_charts(metrics: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "severity": {"labels": ["Critical", "High", "Medium", "Low"], "values": [1, 3, 6, 2]},
        "status": {"labels": ["Week 1", "Week 2", "Week 3", "Week 4"], "open": [8, 6, 7, 4], "closed": [2, 4, 5, 8]},
        "aging": {"labels": ["0-7", "8-14", "15-30", "31+"], "values": [5, 7, 12, 9]},
    }


# Registered user dependency (passwordless auth) — provided by auth router.
# If your auth router exposes get_current_user, import and use it here.
try:
    from .routers.auth import get_current_user
except Exception:
    def get_current_user():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")


# Example persistence stubs — replace with real DB integration (SQLAlchemy models)

def get_user_audit_count(user_id: Any) -> int:
    # TODO: query Railway DB for audit count in the last window
    return 0


def increment_user_audit_count(user_id: Any) -> None:
    # TODO: persist audit record for user
    pass


# PDF generation wrapper (5 pages minimum)

def generate_pdf_report(audit_ctx: Dict[str, Any], output_dir: Path) -> Path:
    """
    Try using your dedicated report module; fall back to a lightweight 5‑page PDF via reportlab.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / f"audit_{datetime.now(TZ_OFFSET).strftime('%Y%m%d_%H%M%S')}.pdf"

    if report is not None and hasattr(report, "build_report"):
        # Your project’s report builder (recommended)
        artifacts = report.build_report(audit_ctx, str(output_dir), formats=["pdf"], title="Website Audit Report", author="FF Tech")
        # Try to resolve the PDF path from artifacts
        for key, val in (artifacts or {}).items():
            if key.endswith("pdf") or str(val).lower().endswith(".pdf"):
                return Path(val)
        # If not found, continue to fallback below

    # Fallback: reportlab-based simple PDF
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.units import cm
    from reportlab.lib import colors

    c = Canvas(str(pdf_path), pagesize=A4)
    width, height = A4

    def header(title: str):
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(2 * cm, height - 2 * cm, f"FF Tech · {title}")
        c.setFont("Helvetica", 9)
        c.drawString(2 * cm, height - 2.8 * cm, f"Generated: {datetime.now(TZ_OFFSET).isoformat()}")
        c.line(2 * cm, height - 3 * cm, width - 2 * cm, height - 3 * cm)

    # Page 1: Executive Summary
    header("Executive Summary")
    c.setFont("Helvetica", 12)
    grade = audit_ctx.get("executive_summary", {}).get("website_grade", "-")
    score = audit_ctx.get("executive_summary", {}).get("overall_site_health_score", 0)
    c.drawString(2 * cm, height - 4 * cm, f"Overall Score: {score}% · Grade: {grade}")
    c.setFont("Helvetica", 10)
    text = c.beginText(2 * cm, height - 5 * cm)
    text.textLines(audit_ctx.get("executive_summary", {}).get("summary", ""))
    c.drawText(text)
    c.showPage()

    # Page 2: Category Breakdown (simple bars)
    header("Category Breakdown")
    c.setFont("Helvetica", 10)
    y = height - 5 * cm
    for cat, val in audit_ctx.get("executive_summary", {}).get("category_breakdown", {}).items():
        c.drawString(2 * cm, y, f"{cat}")
        c.setFillColor(colors.HexColor("#6c5ce7"))
        c.rect(6 * cm, y - 0.3 * cm, (val / 100.0) * (width - 8 * cm), 0.5 * cm, fill=True, stroke=False)
        c.setFillColor(colors.black)
        c.drawString(width - 2.5 * cm, y, f"{val}%")
        y -= 1 * cm
    c.showPage()

    # Page 3: Strengths & Weaknesses
    header("Strengths & Weaknesses")
    c.setFont("Helvetica", 11)
    c.drawString(2 * cm, height - 4 * cm, "Strengths:")
    y = height - 5 * cm
    for s in audit_ctx.get("executive_summary", {}).get("strengths", []):
        c.drawString(2.5 * cm, y, f"• {s}")
        y -= 0.7 * cm
    c.drawString(2 * cm, y - 0.7 * cm, "Weak Areas:")
    y -= 1.4 * cm
    for w in audit_ctx.get("executive_summary", {}).get("weak_areas", []):
        c.drawString(2.5 * cm, y, f"• {w}")
        y -= 0.7 * cm
    c.showPage()

    # Page 4: Priorities & Trends
    header("Priority Fixes & Trends")
    c.setFont("Helvetica", 11)
    c.drawString(2 * cm, height - 4 * cm, "Priority Fixes:")
    y = height - 5 * cm
    for p in audit_ctx.get("executive_summary", {}).get("priority_fixes", []):
        c.drawString(2.5 * cm, y, f"• {p}")
        y -= 0.7 * cm
    # Simple trend
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, y - 1.0 * cm, "Issues Trend (recent):")
    y -= 2.0 * cm
    trend = audit_ctx.get("overall_site_health", {}).get("issues_trend", [])
    for i, v in enumerate(trend):
        c.setFillColor(colors.HexColor("#00d4ff"))
        c.rect(3 * cm + i * 2 * cm, y, 1.2 * cm, v * 0.2 * cm, fill=True, stroke=False)
    c.setFillColor(colors.black)
    c.showPage()

    # Page 5: Conclusion
    header("Conclusion")
    c.setFont("Helvetica", 12)
    c.drawString(2 * cm, height - 4 * cm, "This report is client‑ready and printable.")
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, height - 5 * cm, "FF Tech Branding — Certified Export Ready")
    c.drawString(2 * cm, height - 6 * cm, f"URL: {audit_ctx.get('url', '')}")
    c.drawString(2 * cm, height - 7 * cm, f"Crawled Pages: {audit_ctx.get('overall_site_health', {}).get('total_crawled_pages', '-')}")
    c.showPage()

    c.save()
    return pdf_path


def common_context(request: Request, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {
        "request": request,
        "year": _now_year(),
    }
    if extra:
        ctx.update(extra)
    return ctx


# -----------------------------------------------------------------------------
# Pages (HTML integrated)
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    ctx = {"metrics": {"total_audits": 128, "open_findings": 57, "avg_risk": 72}}
    return templates.TemplateResponse("index.html", common_context(request, ctx))


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    ctx = {
        "kpis": {
            "audits_this_month": 12,
            "closed_findings": 34,
            "high_risk": 7,
            "mean_closure_days": 9,
        },
        "recent_audits": [
            {"id": 101, "title": "Plant A Safety", "owner": "Ops", "status": "Open", "risk": 78, "updated": "2026-01-10"},
            {"id": 102, "title": "Data Center Security", "owner": "IT", "status": "In Progress", "risk": 65, "updated": "2026-01-09"},
            {"id": 103, "title": "Finance Controls", "owner": "Finance", "status": "Closed", "risk": 40, "updated": "2026-01-07"},
        ],
        "charts": build_dashboard_charts(),
    }
    return templates.TemplateResponse("dashboard.html", common_context(request, ctx))


# -----------------------------
# Open Access Audit (no history)
# -----------------------------
@app.get("/open-audit", response_class=HTMLResponse)
async def open_audit(request: Request, url: str):
    if not url or "." not in url:
        raise HTTPException(status_code=400, detail="Please provide a valid website URL")

    result = run_open_audit(url)
    ctx = {
        "audit": {
            "title": f"Open Audit: {url}",
            "owner": "Public",
            "status": "Complete",
            "risk": result["executive_summary"]["overall_site_health_score"],
            "updated": datetime.now(TZ_OFFSET).strftime("%Y-%m-%d"),
        },
        "findings": [
            {"id": "OA-01", "title": "Missing structured data", "severity": "Medium", "status": "Open", "owner": "SEO", "due": "-"},
            {"id": "OA-02", "title": "Large image payloads", "severity": "High", "status": "Open", "owner": "Ops", "due": "-"},
        ],
        "charts": build_audit_detail_charts(result),
    }
    return templates.TemplateResponse("audit_detail.html", common_context(request, ctx))


# -----------------------------
# Registered Audit (history + limits)
# -----------------------------
@app.get("/user/audit", response_class=HTMLResponse)
async def user_audit_get(request: Request, current_user: Any = Depends(get_current_user)):
    # Show form via new_audit.html
    return templates.TemplateResponse("new_audit.html", common_context(request))


@app.post("/user/audit", response_class=HTMLResponse)
async def user_audit_post(request: Request, url: str, current_user: Any = Depends(get_current_user)):
    # Enforce free tier limit: 10 audits
    count = get_user_audit_count(getattr(current_user, "id", None))
    if count >= 10:
        raise HTTPException(status_code=402, detail="Free tier limit reached. Subscribe to continue.")

    result = run_open_audit(url)  # reuse audit logic
    increment_user_audit_count(getattr(current_user, "id", None))

    # Generate PDF report (5 pages min)
    pdf_path = generate_pdf_report(result, EXPORT_DIR)

    ctx = {
        "audit": {
            "title": f"Audit: {url}",
            "owner": getattr(current_user, "email", "User"),
            "status": "Complete",
            "risk": result["executive_summary"]["overall_site_health_score"],
            "updated": datetime.now(TZ_OFFSET).strftime("%Y-%m-%d"),
        },
        "findings": [
            {"id": "RU-01", "title": "Duplicate headings", "severity": "Medium", "status": "Open", "owner": "SEO", "due": "-"},
            {"id": "RU-02", "title": "Uncompressed images", "severity": "High", "status": "Open", "owner": "Ops", "due": "-"},
        ],
        "charts": build_audit_detail_charts(result),
        "report_pdf": f"/download/report/{pdf_path.name}",
    }
    return templates.TemplateResponse("audit_detail.html", common_context(request, ctx))


@app.get("/download/report/{filename}")
async def download_report(filename: str, current_user: Any = Depends(get_current_user)):
    path = EXPORT_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(path)


# -----------------------------
# Other pages
# -----------------------------
@app.get("/new_audit", response_class=HTMLResponse)
async def new_audit(request: Request):
    return templates.TemplateResponse("new_audit.html", common_context(request))


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, current_user: Any = Depends(get_current_user)):
    # Simple list; replace with DB query
    users = [
        {"name": "Alice", "email": "alice@example.com", "role": "Admin", "active": True},
        {"name": "Bob", "email": "bob@example.com", "role": "Auditor", "active": True},
        {"name": "Carol", "email": "carol@example.com", "role": "Viewer", "active": False},
    ]
    return templates.TemplateResponse("admin.html", common_context(request, {"users": users}))


@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    return templates.TemplateResponse("login.html", common_context(request))


@app.get("/register", response_class=HTMLResponse)
async def register(request: Request):
    return templates.TemplateResponse("register.html", common_context(request))


@app.get("/verify", response_class=HTMLResponse)
async def verify(request: Request):
    return templates.TemplateResponse("verify.html", common_context(request))


# -----------------------------
# Existing routers
# -----------------------------
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(audits.router)
app.include_router(pages.router)
