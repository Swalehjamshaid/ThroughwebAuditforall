from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import db_session
from app.models import Audit
from app.audit.analyzer import run_200_metric_audit
from app.audit.grader import compute_category_scores, grade_from_score

router = APIRouter(prefix='/audit', tags=['audit'])

# This model defines the JSON body the backend expects
class AuditRequest(BaseModel):
    url: str

@router.post('/run')
async def run_audit(payload: AuditRequest, db: Session = Depends(db_session)):
    # Extract the URL from the JSON payload
    url = payload.url
    
    # 1. Run the analysis logic
    results, raw_avg = await run_200_metric_audit(url)
    score, cat_scores, summary = compute_category_scores(results)
    grade = grade_from_score(score)

    # 2. Save to database
    new_audit = Audit(
        url=url,
        score=int(score),
        grade=grade,
        result={'categories': cat_scores} 
    )
    db.add(new_audit)
    db.commit()
    db.refresh(new_audit)

    return {
        "id": new_audit.id,
        "score": score,
        "grade": grade,
        "categories": cat_scores
    }
