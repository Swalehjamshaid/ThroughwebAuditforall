from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..database import get_db
from ..schemas import AuditRequest, AuditResponse
from ..models import User, AuditJob, AuditResult
from ..audit.metrics import compute_metrics
from ..audit.scoring import score_category, overall_score, letter_grade
from ..audit.report import generate_pdf
from ..audit.record import save_charts_png, save_excel, save_pptx
import os

router = APIRouter(prefix='/api', tags=['audit'])


def _current_user(request: Request, db: Session) -> User | None:
    if request.cookies.get('session') and request.headers.get('X-User-Email'):
        email = request.headers['X-User-Email'].lower()
        return db.query(User).filter_by(email=email).first()
    return None

@router.post('/audit', response_model=AuditResponse)
async def run_audit(payload: AuditRequest, request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if user and not user.is_subscribed:
        count = db.query(AuditJob).filter_by(user_id=user.id).count()
        from ..config import get_settings
        if count >= get_settings().FREE_AUDIT_LIMIT:
            raise HTTPException(status_code=402, detail='Free audit limit reached (subscribe for more)')

    url = payload.url
    metrics = compute_metrics(url)
    categories = score_category(metrics)
    overall = overall_score(categories)
    grade = letter_grade(overall)

    out_dir = 'data/reports'; os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, f"report_{grade}_{os.getpid()}.pdf")
    charts = save_charts_png(out_dir, metrics, categories)
    generate_pdf(pdf_path, url, metrics, categories, overall, grade)
    excel_path = os.path.join(out_dir, 'summary.xlsx'); save_excel(excel_path, metrics, categories)
    pptx_path = os.path.join(out_dir, 'summary.pptx'); save_pptx(pptx_path, charts, pdf_path)

    if user:
        job = AuditJob(user_id=user.id, target_url=url, status='completed'); db.add(job); db.commit(); db.refresh(job)
        result = AuditResult(job_id=job.id, metrics=metrics, scores={**categories, 'overall': overall, 'grade': grade}, pdf_path=pdf_path)
        db.add(result); db.commit()
        return AuditResponse(audit_id=job.id, target_url=url, scores=result.scores, metrics=metrics, pdf_url=f"/api/report/pdf/{job.id}")
    else:
        return AuditResponse(audit_id=None, target_url=url, scores={**categories, 'overall': overall, 'grade': grade}, metrics=metrics, pdf_url=None)

@router.get('/audit/{audit_id}', response_model=AuditResponse)
async def get_audit(audit_id: int, request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user: raise HTTPException(status_code=401, detail='Login required')
    job = db.query(AuditJob).filter_by(id=audit_id, user_id=user.id).first()
    if not job or not job.result: raise HTTPException(status_code=404, detail='Audit not found')
    r = job.result
    return AuditResponse(audit_id=job.id, target_url=job.target_url, scores=r.scores, metrics=r.metrics, pdf_url=f"/api/report/pdf/{job.id}")

@router.get('/report/pdf/{audit_id}')
async def get_pdf(audit_id: int, request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    user = _current_user(request, db)
    if not user: raise HTTPException(status_code=401, detail='Login required')
    job = db.query(AuditJob).filter_by(id=audit_id, user_id=user.id).first()
    if not job or not job.result: raise HTTPException(status_code=404, detail='Audit not found')
    return FileResponse(job.result.pdf_path, media_type='application/pdf', filename=f'FFTech_Audit_{audit_id}.pdf')
