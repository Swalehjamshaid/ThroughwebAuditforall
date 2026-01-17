import os
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from .config import settings
from .database import init_db, SessionLocal
from .models import User, Audit
from .routers import auth as auth_router
from .audit.analyzer import analyze
from .audit.grader import overall_score, to_grade
from .audit.report import build_pdf
from .audit.record import export_graphs, export_pptx, export_xlsx

app = FastAPI(title=f"{settings.BRAND_NAME} AI Website Audit")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = os.path.join(os.path.dirname(__file__), 'static')
app.mount('/static', StaticFiles(directory=static_dir), name='static')

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), 'templates'))

app.include_router(auth_router.router)

@app.on_event("startup")
def on_startup():
    init_db()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# UI pages (your existing routes)
@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ... (keep all your other routes: /open-audit, /login, /register, /verify, /dashboard, etc.)

# API endpoint (your existing one)
from .schemas import AuditRequest, AuditResponse

@app.post("/api/audit", response_model=AuditResponse)
async def run_audit(payload: AuditRequest, db: Session = Depends(get_db), email: str | None = None):
    url = payload.url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
    result = await analyze(url, payload.competitors)
    ovr = overall_score(result["category_scores"])
    grade = to_grade(ovr)
    summary = {
        "executive_summary": f"Automated audit for {url}. Reduce errors, improve metadata and performance.",
        "strengths": ["Crawlability baseline OK"],
        "weaknesses": ["Missing titles/descriptions", "Performance improvements needed"],
        "priority_fixes": ["Fix 4xx/5xx", "Add meta descriptions", "Optimize images"]
    }
    audit_id = None
    if email:
        user = db.query(User).filter(User.email == email).first()
        if user and user.subscription == "free":
            count = db.query(Audit).filter(Audit.user_id == user.id).count()
            if count >= 10:
                raise HTTPException(status_code=402, detail="Free tier limit reached (10 audits)")
        if user:
            audit = Audit(
                user_id=user.id,
                url=url,
                overall_score=ovr,
                grade=grade,
                summary=summary,
                category_scores=result["category_scores"],
                metrics=result["metrics"]
            )
            db.add(audit)
            db.commit()
            db.refresh(audit)
            audit_id = audit.id
            pdf = build_pdf(
                audit.id, url, ovr, grade,
                result["category_scores"], result["metrics"],
                out_dir="storage/reports"
            )
            audit.report_pdf_path = pdf
            db.commit()
            png = export_graphs(audit.id, result["category_scores"], out_dir="storage/exports")
            export_xlsx(audit.id, result["metrics"], result["category_scores"], out_dir="storage/exports")
            export_pptx(audit.id, png, result["metrics"], out_dir="storage/exports")
    return AuditResponse(
        audit_id=audit_id,
        url=url,
        overall_score=ovr,
        grade=grade,
        summary=summary,
        category_scores=result["category_scores"],
        metrics=result["metrics"]
    )

# ... keep your other endpoints (e.g. /api/reports/pdf/{audit_id})
