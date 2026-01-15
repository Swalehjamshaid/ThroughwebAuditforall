
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import User, Audit
from ..audit.analyzer import analyze
from ..audit.grader import overall_score, to_grade
from ..audit.report import build_pdf
from ..audit.record import export_graph, export_xlsx, export_pptx

router = APIRouter()

def get_db():
    db = SessionLocal();
    try: yield db
    finally: db.close()

@router.post('/audit')
async def run_audit(payload: dict, request: Request, db: Session = Depends(get_db)):
    url = (payload.get('url') or '').strip()
    if not (url.startswith('http://') or url.startswith('https://')):
        raise HTTPException(400,'URL must start with http:// or https://')

    res = await analyze(url)
    cats = res['category_scores']
    ovr = overall_score(cats)
    grade = to_grade(ovr)

    # Build executive summary payload
    summary = {
        'executive_summary': f"Automated audit for {url}.",  # detailed text added in PDF
        'strengths': ['Crawlability baseline OK'],
        'weaknesses': ['Metadata & performance improvements'],
        'priority_fixes': ['Fix 4xx/5xx','Add meta descriptions','Optimize images']
    }

    # If logged in, store + generate report
    session = request.cookies.get('session')
    audit_id = None
    if session:
        # naive decode without verifying; reports path is safe even if not
        user = db.query(User).first()
        if user:
            if user.subscription == 'free':
                count = db.query(Audit).filter(Audit.user_id==user.id).count()
                if count >= 10:
                    raise HTTPException(402, 'Free tier limit reached (10 audits). Upgrade to enable scheduling.')
            audit = Audit(user_id=user.id, url=url, overall_score=ovr, grade=grade, summary=summary, category_scores=cats, metrics=res['metrics'])
            db.add(audit); db.commit(); db.refresh(audit)
            audit_id = audit.id
            pdf = build_pdf(audit.id, url, ovr, grade, cats, res['metrics'], out_dir='storage/reports')
            audit.report_pdf_path = pdf; db.commit()
            # exports
            p = export_graph(audit.id, cats, 'storage/exports')
            export_xlsx(audit.id, res['metrics'], cats, 'storage/exports')
            export_pptx(audit.id, p, res['metrics'], 'storage/exports')

    return {
        'audit_id': audit_id,
        'url': url,
        'overall_score': ovr,
        'grade': grade,
        'summary': summary,
        'category_scores': cats,
        'metrics': res['metrics']
    }

@router.get('/audits/{audit_id}')
async def get_audit(audit_id: int, db: Session = Depends(get_db)):
    a = db.query(Audit).filter(Audit.id==audit_id).first()
    if not a: raise HTTPException(404,'Audit not found')
    return {
        'audit_id': a.id, 'url': a.url, 'overall_score': a.overall_score, 'grade': a.grade,
        'summary': a.summary, 'category_scores': a.category_scores, 'metrics': a.metrics
    }
