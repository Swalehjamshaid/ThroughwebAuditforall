from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel # Added for JSON validation
import io, tempfile, zipfile

from ..db import db_session
from ..models import User, Audit
from ..audit.analyzer import analyze
from ..audit.grader import compute_category_scores, grade_from_score
from ..audit.report import build_pdf
from ..audit.record import save_png_summary, save_xlsx, save_pptx

router = APIRouter(prefix='/audit', tags=['audit'])

# --- NEW: Pydantic models to fix the 422 error ---
class AuditRequest(BaseModel):
    url: str

class RegisteredAuditRequest(BaseModel):
    url: str
    user_email: str

@router.get('/open', response_class=HTMLResponse)
def open_form(request: Request):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory='app/templates')
    return templates.TemplateResponse('index.html', {'request': request})

@router.post('/run')
def run_audit(payload_in: AuditRequest, request: Request, db: Session = Depends(db_session)):
    # Use payload_in.url instead of a raw url string to parse JSON
    url = payload_in.url
    payload = analyze(url)
    overall, cat_scores = compute_category_scores(payload['results'])
    grade = grade_from_score(overall)
    return {'url': url, 'score': overall, 'grade': grade, 'categories': cat_scores, 'details': payload}

@router.post('/run-registered')
def run_audit_registered(payload_in: RegisteredAuditRequest, request: Request, db: Session = Depends(db_session)):
    # Use the Pydantic model to extract data from the JSON body
    user_email = payload_in.user_email
    url = payload_in.url
    
    user = db.query(User).filter(User.email==user_email).first()
    if not user:
        raise HTTPException(status_code=401, detail='User not found. Please sign in.')
    
    payload = analyze(url)
    overall, cat_scores = compute_category_scores(payload['results'])
    grade = grade_from_score(overall)
    audit = Audit(user_id=user.id, url=url, result={'categories': cat_scores, 'details': payload}, grade=grade, score=int(overall))
    db.add(audit)
    db.commit()
    return {'id': audit.id, 'url': url, 'score': overall, 'grade': grade, 'categories': cat_scores}

@router.get('/{audit_id}/pdf')
def audit_pdf(audit_id: int, db: Session = Depends(db_session)):
    audit = db.query(Audit).filter(Audit.id==audit_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail='Audit not found')
    payload = audit.result['details']
    overall = float(audit.score)
    cat_scores = audit.result['categories']
    pdf_bytes = build_pdf(payload, overall, cat_scores, audit.url)
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type='application/pdf', headers={'Content-Disposition': f'inline; filename="audit_{audit_id}.pdf"'})

@router.get('/{audit_id}/exports')
def audit_exports(audit_id: int, db: Session = Depends(db_session)):
    audit = db.query(Audit).filter(Audit.id==audit_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail='Audit not found')

    tmpdir = tempfile.mkdtemp()
    png_path = f"{tmpdir}/summary.png"
    xlsx_path = f"{tmpdir}/metrics.xlsx"
    pptx_path = f"{tmpdir}/summary.pptx"

    save_png_summary(audit.result['categories'], png_path)
    save_xlsx(audit.result['details']['results'], xlsx_path)
    save_pptx(audit.score, audit.grade, audit.result['categories'], png_path, pptx_path)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(png_path, 'summary.png')
        zf.write(xlsx_path, 'metrics.xlsx')
        zf.write(pptx_path, 'summary.pptx')
    zip_buf.seek(0)
    return StreamingResponse(zip_buf, media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="audit_{audit_id}_exports.zip"'})
