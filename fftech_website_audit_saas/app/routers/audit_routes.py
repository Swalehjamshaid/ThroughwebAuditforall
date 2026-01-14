from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

# FIXED: Absolute imports for Railway stability
from app.database import db_session
from app.models import User, Audit
from app.audit.analyzer import run_200_metric_audit # Matches your analyzer function
from app.audit.grader import compute_category_scores, grade_from_score

router = APIRouter(prefix='/audit', tags=['audit'])

class AuditRequest(BaseModel):
    url: str
    user_email: Optional[str] = None

@router.post('/run')
async def run_audit(payload: AuditRequest, db: Session = Depends(db_session)):
    user = None
    if payload.user_email:
        user = db.query(User).filter(User.email == payload.user_email).first()
        if user and not user.is_subscriber and user.audit_count >= 10:
            raise HTTPException(status_code=403, detail="Free user limit reached.")

    # FIXED: Calling the correctly named function
    results, raw_score = await run_200_metric_audit(payload.url)
    
    score, cat_scores, summary = compute_category_scores(results)
    grade = grade_from_score(score)

    new_audit = Audit(
        user_id=user.id if user else None, 
        url=payload.url, 
        score=int(score), 
        grade=grade, 
        result={'categories': cat_scores, 'summary': summary}
    )
    
    if user: 
        user.audit_count += 1
        
    db.add(new_audit)
    db.commit()
    db.refresh(new_audit)

    return {"id": new_audit.id, "score": score, "grade": grade, "summary": summary, "categories": cat_scores}
