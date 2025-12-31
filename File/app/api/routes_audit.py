
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session
import io, uuid

from app.core.authz import get_db, get_current_user, require_roles
from app.core.pdf import build_pdf
from app.services.audit_engine import AuditEngine
from app.db.models import Audit, AuditMetric

router = APIRouter()

class AuditRequest(BaseModel):
    url: HttpUrl

@router.post("/audit")
def audit(req: AuditRequest, request: Request, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    engine = AuditEngine(str(req.url))
    metrics, categories, overall, grade = engine.run()
    audit_id = str(uuid.uuid4())
    row = Audit(
        id=audit_id,
        site_url=str(req.url),
        overall_score=int(overall),
        grade=str(grade),
        result=metrics,
        user_id=getattr(current_user, 'id', None)
    )
    db.add(row)
    db.flush()
    # Persist category metrics with code=0
    for cat, score in categories.items():
        metric = AuditMetric(
            audit_id=audit_id,
            category=cat,
            code=0,
            name="Category Score",
            value=int(score)
        )
        db.add(metric)
    db.commit()
    return {"audit_id": audit_id, "result": {"overall_score": overall, "grade": grade, "categories": {k:{"score":v} for k,v in categories.items()} , "metrics": metrics}}

@router.get("/audit/{audit_id}")
def get_audit(audit_id: str, db: Session = Depends(get_db)):
    row = db.query(Audit).filter(Audit.id == audit_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Audit not found")
    return {
        "audit_id": row.id,
        "site": row.site_url,
        "overall_score": row.overall_score,
        "grade": row.grade,
        "result": row.result,
        "created_at": row.created_at.isoformat() + "Z",
        "user_id": row.user_id,
    }

@router.get("/audit/{audit_id}/metrics")
def get_metrics(audit_id: str, db: Session = Depends(get_db)):
    rows = db.query(AuditMetric).filter(AuditMetric.audit_id == audit_id).all()
    if not rows:
        audit = db.query(Audit).filter(Audit.id == audit_id).first()
        if not audit:
            raise HTTPException(status_code=404, detail="Audit not found")
        return []
    return [
        {
            "id": m.id,
            "category": m.category,
            "code": m.code,
            "name": m.name,
            "value": m.value,
            "severity": m.severity,
            "impact": m.impact,
            "priority": m.priority,
            "created_at": m.created_at.isoformat() + "Z",
        }
        for m in rows
    ]

@router.get("/admin/audits")
def list_audits_admin(db: Session = Depends(get_db), user = Depends(require_roles("admin"))):
    rows = db.query(Audit).order_by(Audit.created_at.desc()).limit(50).all()
    return [{
        "audit_id": r.id,
        "site": r.site_url,
        "overall_score": r.overall_score,
        "grade": r.grade,
        "user_id": r.user_id,
        "created_at": r.created_at.isoformat() + "Z",
    } for r in rows]

@router.get("/report/{audit_id}")
def report(audit_id: str, db: Session = Depends(get_db)):
    row = db.query(Audit).filter(Audit.id == audit_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Audit not found")
    buffer = io.BytesIO()
    build_pdf(buffer, audit_id)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={
        "Content-Disposition": f"inline; filename=fftech_audit_{audit_id}.pdf"
    })
