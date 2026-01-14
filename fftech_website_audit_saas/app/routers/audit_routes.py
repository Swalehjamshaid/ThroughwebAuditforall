from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel  # Required for JSON parsing
import io, tempfile, zipfile

from ..db import db_session
from ..models import User, Audit
from ..audit.analyzer import analyze
from ..audit.grader import compute_category_scores, grade_from_score
from ..audit.report import build_pdf
from ..audit.record import save_png_summary, save_xlsx, save_pptx

router = APIRouter(prefix='/audit', tags=['audit'])

# --- NEW: Schema Definitions to fix the 422 error ---
class AuditRequest(BaseModel):
    """Schema for Open Access audits."""
    url: str

class RegisteredAuditRequest(BaseModel):
    """Schema for Registered User audits."""
    url: str
    user_email: str

@router.get('/open', response_class=HTMLResponse)
def open_form(request: Request):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory='app/templates')
    return templates.TemplateResponse('index.html', {'request': request})

@router.post('/run')
def run_audit(payload_in: AuditRequest, db: Session = Depends(db_session)):
    """
    Handles Open Access Audit. 
    Expects JSON: {"url": "https://example.com"}
    """
    url = payload_in.url
    payload = analyze(url)
    overall, cat_scores = compute_category_scores(payload['results'])
    grade = grade_from_score(overall)
    return {
        'url': url, 
        'score': overall, 
        'grade': grade, 
        'categories': cat_scores, 
        'details': payload
    }

@router.post('/run-registered')
def run_audit_registered(payload_in: RegisteredAuditRequest, db: Session = Depends(db_session)):
    """
    Handles Registered User Audit.
    Expects JSON: {"url": "...", "user_email": "..."}
    """
    user_email = payload_in.user_email
    url = payload_in.url
    
    user = db.query(User).filter(User.email == user_email).first()
    if not user:
        raise HTTPException(status_code=401, detail='User not found. Please sign in.')
    
    payload = analyze(url)
    overall, cat_scores = compute_category_scores(payload['results'])
    grade = grade_from_score(overall)
    
    # Store the audit history
    audit = Audit(
        user_id=user.id, 
        url=url, 
        result={'categories': cat_scores, 'details': payload}, 
        grade=grade, 
        score=int(overall)
    )
    db.add(audit)
    db.commit()
    
    return {
        'id': audit.id, 
        'url': url, 
        'score': overall, 
        'grade': grade, 
        'categories': cat_scores
    }

# Remaining GET routes (pdf and exports) do not need changes 
# as they use path parameters which FastAPI handles differently.
