from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
import io, tempfile, zipfile

from ..db import db_session
from ..models import User, Audit
from ..audit.analyzer import analyze
from ..audit.grader import compute_category_scores, grade_from_score
from ..audit.report import build_pdf
from ..audit.record import save_png_summary, save_xlsx, save_pptx

router = APIRouter(prefix='/audit', tags=['audit'])

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
async def run_audit(payload_in: AuditRequest, db: Session = Depends(db_session)):
    url = payload_in.url
    # Added 'await' to fix the coroutine error
    payload = await analyze(url)
    
    overall, cat_scores = compute_category_scores(payload['results'])
    grade = grade_from_score(overall)
    
    # We save a guest audit so they can download the PDF
    audit = Audit(url=url, result={'categories': cat_scores, 'details': payload}, grade=grade, score=int(overall))
    db.add(audit)
    db.commit()
    db.refresh(audit)
    
    return {
        'id': audit.id,
        'url': url, 
        'score': overall, 
        'grade': grade, 
        'categories': cat_scores, 
        'details': payload
    }

@router.post('/run-registered')
async def run_audit_registered(payload_in: RegisteredAuditRequest, db: Session = Depends(db_session)):
    user = db.query(User).filter(User.email == payload_in.user_email).first()
    if not user:
        raise HTTPException(status_code=401, detail='User not found.')
    
    payload = await analyze(payload_in.url)
    overall, cat_scores = compute_category_scores(payload['results'])
    grade = grade_from_score(overall)
    
    audit = Audit(user_id=user.id, url=payload_in.url, result={'categories': cat_scores, 'details': payload}, grade=grade, score=int(overall))
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return {'id': audit.id, 'url': payload_in.url, 'score': overall, 'grade': grade, 'categories': cat_scores}

@router.get('/{audit_id}/pdf')
def audit_pdf(audit_id: int, db: Session = Depends(db_session)):
    audit = db.query(Audit).filter(Audit.id == audit_id).first()
    if not audit: raise HTTPException(status_code=404)
    pdf_bytes = build_pdf(audit.result['details'], float(audit.score), audit.result['categories'], audit.url)
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type='application/pdf')
