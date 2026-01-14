from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import db_session
from app.models import Audit
from app.audit.analyzer import run_200_metric_audit
from app.audit.grader import compute_category_scores, grade_from_score
from app.audit.report import generate_professional_pdf

router = APIRouter(prefix='/audit', tags=['audit'])

# Define the expected data structure
class AuditRequest(BaseModel):
    url: str

@router.post('/run')
async def run_audit(payload: AuditRequest, db: Session = Depends(db_session)):
    # Use payload.url instead of just url
    url = payload.url
    
    results, raw_avg = await run_200_metric_audit(url)
    score, cat_scores, summary = compute_category_scores(results)
    grade = grade_from_score(score)

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
