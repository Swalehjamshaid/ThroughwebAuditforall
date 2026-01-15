from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from .db import SessionLocal
from .models import User, Audit
from .audit.analyzer import analyze
from .audit.grader import overall_score, to_grade
from .audit.report import build_pdf
from .audit.record import export_graphs, export_pptx, export_xlsx

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post('/audit')
async def run_audit(payload: dict, x_user_email: str | None = None):
    url = (payload.get('url') or '').strip()
    competitors = payload.get('competitors')
    if not url.startswith(('http://','https://')):
        raise HTTPException(status_code=400, detail='URL must start with http:// or https://')

    result = await analyze(url, competitors)
    category_scores = result['category_scores']
    ovr = overall_score(category_scores)
    grade = to_grade(ovr)

    summary = {
        'executive_summary': f"Automated audit for {url}. Focus on reducing errors and improving on-page metadata and performance.",
        'strengths': ['Crawlability baseline OK'],
        'weaknesses': ['Missing titles/descriptions', 'Performance improvements needed'],
        'priority_fixes': ['Fix 4xx/5xx', 'Add meta descriptions', 'Optimize images']
    }

    user = None
    if x_user_email:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email==x_user_email).first()
        finally:
            db.close()

    audit_id = None
    if user:
        db = SessionLocal()
        try:
            if user.subscription == 'free':
                count = db.query(Audit).filter(Audit.user_id==user.id).count()
                if count >= 10:
                    raise HTTPException(status_code=402, detail='Free tier limit reached (10 audits). Upgrade to schedule.')
            audit = Audit(user_id=user.id, url=url, overall_score=ovr, grade=grade, summary=summary, category_scores=category_scores, metrics=result['metrics'])
            db.add(audit)
            db.commit()
            db.refresh(audit)
            audit_id = audit.id
            pdf = build_pdf(audit.id, url, ovr, grade, category_scores, result['metrics'], out_dir='app/storage/reports')
            audit.report_pdf_path = pdf
            db.commit()
            png = export_graphs(audit.id, category_scores, out_dir='app/storage/exports')
            export_xlsx(audit.id, result['metrics'], category_scores, out_dir='app/storage/exports')
            export_pptx(audit.id, png, result['metrics'], out_dir='app/storage/exports')
        finally:
            db.close()

    return {
        'audit_id': audit_id,
        'url': url,
        'overall_score': ovr,
        'grade': grade,
        'summary': summary,
        'category_scores': category_scores,
        'metrics': result['metrics']
    }

@router.get('/audits/{audit_id}')
async def get_audit(audit_id: int):
    db = SessionLocal()
    try:
        audit = db.query(Audit).filter(Audit.id==audit_id).first()
        if not audit:
            raise HTTPException(status_code=404, detail='Audit not found')
        return {
            'audit_id': audit.id,
            'url': audit.url,
            'overall_score': audit.overall_score,
            'grade': audit.grade,
            'summary': audit.summary,
            'category_scores': audit.category_scores,
            'metrics': audit.metrics,
        }
    finally:
        db.close()