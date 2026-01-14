from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel # Add this import
import io, tempfile, zipfile

from ..db import db_session
from ..models import User, Audit
from ..audit.analyzer import analyze
from ..audit.grader import compute_category_scores, grade_from_score
# ... other imports ...

router = APIRouter(prefix='/audit', tags=['audit'])

# --- ADD THESE CLASSES TO FIX THE 422 ERROR ---
class AuditRequest(BaseModel):
    url: str

class RegisteredAuditRequest(BaseModel):
    url: str
    user_email: str

@router.post('/run')
def run_audit(payload: AuditRequest, db: Session = Depends(db_session)):
    """Handles JSON body: {"url": "https://..."}"""
    url = payload.url
    results_data = analyze(url)
    overall, cat_scores = compute_category_scores(results_data['results'])
    grade = grade_from_score(overall)
    return {
        'url': url, 
        'score': overall, 
        'grade': grade, 
        'categories': cat_scores, 
        'details': results_data
    }

@router.post('/run-registered')
def run_audit_registered(payload: RegisteredAuditRequest, db: Session = Depends(db_session)):
    """Handles JSON body: {"url": "...", "user_email": "..."}"""
    user = db.query(User).filter(User.email == payload.user_email).first()
    if not user:
        raise HTTPException(status_code=401, detail='User not found.')
        
    results_data = analyze(payload.url)
    overall, cat_scores = compute_category_scores(results_data['results'])
    grade = grade_from_score(overall)
    
    audit = Audit(
        user_id=user.id, 
        url=payload.url, 
        result={'categories': cat_scores, 'details': results_data}, 
        grade=grade, 
        score=int(overall)
    )
    db.add(audit)
    db.commit()
    return {'id': audit.id, 'url': payload.url, 'score': overall, 'grade': grade}
