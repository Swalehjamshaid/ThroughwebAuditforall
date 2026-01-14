from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from app.database import db_session
from app.models import Audit
from app.audit.analyzer import run_200_metric_audit
from app.audit.grader import compute_category_scores, grade_from_score
from app.audit.report import generate_professional_pdf

router = APIRouter(prefix='/audit', tags=['audit'])

@router.post('/run')
async def run_audit(url: str, db: Session = Depends(db_session)):
    try:
        # 1. Trigger the Backend Analyzer
        results, raw_data = await run_200_metric_audit(url)
        
        # 2. Calculate the Graphical Scores
        score, cat_scores, summary = compute_category_scores(results)
        grade = grade_from_score(score)

        # 3. Save to PostgreSQL
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/{audit_id}/pdf')
async def download_pdf(audit_id: int, db: Session = Depends(db_session)):
    audit = db.query(Audit).filter(Audit.id == audit_id).first()
    if not audit: raise HTTPException(status_code=404)
    
    pdf_bytes = generate_professional_pdf(audit.result['categories'], audit.url, audit.score, audit.grade)
    return Response(content=pdf_bytes, media_type="application/pdf")
