import asyncio
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from ..database import SessionLocal
from .. import models
from ..schemas import AuditRequest, AuditResponse
from ..audit.analyzer import analyze
from ..audit.grader import overall_score, to_grade
from ..audit.report import build_pdf
from ..audit.record import export_graphs, export_pptx, export_xlsx

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post('/audit', response_model=AuditResponse)
async def run_audit(payload: AuditRequest, db: Session = Depends(get_db), x_user_email: str | None = None):
    url = payload.url.strip()
    if not (url.startswith('http://') or url.startswith('https://')):
        raise HTTPException(status_code=400, detail='URL must start with http:// or https://')

    result = await analyze(url, payload.competitors)
    category_scores = result['category_scores']
    ovr = overall_score(category_scores)
    grade = to_grade(ovr)

    summary = {
        'executive_summary': f"Automated audit for {url}. Focus on crawl errors, metadata and performance.",
        'strengths': ['Crawlability baseline OK'],
        'weaknesses': ['Missing titles/descriptions', 'Performance improvements needed'],
        'priority_fixes': ['Fix 4xx/5xx', 'Add meta descriptions', 'Optimize images']
    }

    user = None
    if x_user_email:
        user = db.query(models.User).filter(models.User.email == x_user_email).first()

    audit_id = None
    if user:
        if user.subscription == 'free':
            count = db.query(models.Audit).filter(models.Audit.user_id == user.id).count()
            if count >= 10:
                raise HTTPException(status_code=402, detail='Free tier limit reached (10 audits). Upgrade to schedule.')
        audit = models.Audit(
            user_id=user.id, url=url, overall_score=ovr, grade=grade,
            summary=summary, category_scores=category_scores, metrics=result['metrics']
        )
        db.add(audit); db.commit(); db.refresh(audit)
        audit_id = audit.id
        pdf_path = build_pdf(audit.id, url, ovr, grade, category_scores, result['metrics'], out_dir='storage/reports', competitors=result.get('competitors'))
        audit.report_pdf_path = pdf_path; db.commit()
        png = export_graphs(audit.id, category_scores, out_dir='storage/exports')
        export_xlsx(audit.id, result['metrics'], category_scores, out_dir='storage/exports')
        export_pptx(audit.id, png, result['metrics'], out_dir='storage/exports', competitors=result.get('competitors'))

    return AuditResponse(
        audit_id=audit_id, url=url, overall_score=ovr, grade=grade, summary=summary,
        category_scores=category_scores, metrics=result['metrics'], competitors=result.get('competitors')
    )

@router.get('/audits/{audit_id}', response_model=AuditResponse)
async def get_audit(audit_id: int, db: Session = Depends(get_db)):
    audit = db.query(models.Audit).filter(models.Audit.id == audit_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail='Audit not found')
    return AuditResponse(
        audit_id=audit.id, url=audit.url, overall_score=audit.overall_score,
        grade=audit.grade, summary=audit.summary, category_scores=audit.category_scores, metrics=audit.metrics
    )