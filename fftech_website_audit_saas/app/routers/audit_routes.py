from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import db_session
from app.models import User, Audit
from app.audit.analyzer import run_200_metric_audit # Correct Function Name
from app.audit.grader import compute_category_scores, grade_from_score

router = APIRouter(prefix='/audit', tags=['audit'])

@router.post('/run')
async def run_audit(url: str, email: str = None, db: Session = Depends(db_session)):
    user = db.query(User).filter(User.email == email).first() if email else None
    
    # Execute the 200-metric engine
    results, raw_score = await run_200_metric_audit(url)
    
    score, cat_scores, summary = compute_category_scores(results)
    grade = grade_from_score(score)

    new_audit = Audit(
        user_id=user.id if user else None,
        url=url,
        score=int(score),
        grade=grade,
        result={'categories': cat_scores, 'summary': summary}
    )
    if user: user.audit_count += 1
    
    db.add(new_audit)
    db.commit()
    return {"id": new_audit.id, "score": score, "grade": grade}
