
from fastapi import FastAPI, Request, Form, Body, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from .audit_engine import AuditEngine, canonical_origin, aggregate_score, grade_from_score, METRIC_DESCRIPTORS
from .db import SessionLocal, User, Audit
from .auth_email import send_verification_link, verify_session_token
from .ui_and_pdf import build_pdf_report
import json, io

app = FastAPI(title="FF Tech AI Website Audit SaaS")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="fftech_audit/templates")

@app.post("/audit/open", response_class=HTMLResponse)
async def audit_open_ssr(request: Request, url: str = Form(...)):
    origin = canonical_origin(url)
    eng = AuditEngine(origin)
    metrics = eng.compute_metrics()
    score, category_scores = aggregate_score({
        "security": {"https_enabled": True}, "performance": {"ttfb_ms": 300}
    })
    grade = grade_from_score(score)
    return templates.TemplateResponse("results.html", {
        "request": request, "url": url, "url_display": origin,
        "score": score, "grade": grade, "category_scores": category_scores,
        "rows": [{"id": i, "name": METRIC_DESCRIPTORS[i]["name"], "category": METRIC_DESCRIPTORS[i]["category"], "value": metrics.get(i, {}).get("value", "N/A")} for i in range(1, 201)]
    })

@app.post("/api/report/pdf")
async def report_pdf_api(req: dict = Body(...)):
    token = req.get('token'); email = verify_session_token(token).get('email')
    url = req.get('url'); origin = canonical_origin(url)
    eng = AuditEngine(origin); metrics = eng.compute_metrics()
    score, category_scores = aggregate_score({"security": {"https_enabled": True}, "performance": {"ttfb_ms": 300}})
    grade = grade_from_score(score)
    audit = Audit(user_id=None, url=origin, metrics_json=json.dumps(metrics), score=int(score), grade=grade)
    pdf_bytes = build_pdf_report(audit, category_scores, metrics.get(4, {}).get("value", []), metrics.get(5, {}).get("value", []), metrics.get(6, {}).get("value", []))
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=FFTech_Audit.pdf"})
