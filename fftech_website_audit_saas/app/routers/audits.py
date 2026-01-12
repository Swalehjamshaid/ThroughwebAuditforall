
from __future__ import annotations
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import User, Audit
from ..services.audit_service import audit_url
from ..services.grader import compute_overall_grade
from ..services.report_service import generate_pdf_report
from ..config import FREE_AUDIT_LIMIT, FREE_HISTORY_DAYS, SECRET_KEY, JWT_ALGORITHM
import jwt

router = APIRouter(prefix="/audits", tags=["audits"])
security = HTTPBearer(auto_error=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(creds: HTTPAuthorizationCredentials | None, db: Session) -> User | None:
    if not creds:
        return None
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        email = payload.get("sub")
        return db.query(User).filter(User.email == email).first() if email else None
    except Exception:
        return None

@router.post("/open")
async def run_open_audit(url: str):
    data = audit_url(url)
    overall_score, grade = compute_overall_grade(data.get("category_scores", {}))
    data["overall"] = {"score": overall_score, "grade": grade}
    pdf_path = generate_pdf_report({"url": url, **data})
    data["pdf"] = str(pdf_path)
    return data

@router.post("/secure")
async def run_secure_audit(url: str, creds: HTTPAuthorizationCredentials | None = Depends(security), db: Session = Depends(get_db)):
    user = get_current_user(creds, db)
    if not user or not user.email_verified:
        raise HTTPException(status_code=401, detail="Unauthorized or email not verified")
    if not user.subscription_active and user.audits_count >= FREE_AUDIT_LIMIT:
        raise HTTPException(status_code=403, detail="Free audit limit reached")
    data = audit_url(url)
    overall_score, grade = compute_overall_grade(data.get("category_scores", {}))
    data["overall"] = {"score": overall_score, "grade": grade}
    expires_at = datetime.utcnow() + timedelta(days=FREE_HISTORY_DAYS if not user.subscription_active else 365)
    audit = Audit(user_id=user.id, url=url, metrics_json=json.dumps(data), overall_score=overall_score, grade=grade, expires_at=expires_at)
    db.add(audit)
    user.audits_count += 1
    db.commit()
    pdf_path = generate_pdf_report({"url": url, **data})
    return {"id": audit.id, "pdf": str(pdf_path), "overall": data["overall"], "category_scores": data.get("category_scores", {})}

@router.get("")
async def list_audits(creds: HTTPAuthorizationCredentials | None = Depends(security), db: Session = Depends(get_db)):
    user = get_current_user(creds, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    now = datetime.utcnow()
    audits = db.query(Audit).filter(Audit.user_id == user.id, (Audit.expires_at == None) | (Audit.expires_at > now)).order_by(Audit.created_at.desc()).limit(100).all()
    return [{"id": a.id, "url": a.url, "overall_score": a.overall_score, "grade": a.grade, "created_at": a.created_at.isoformat()} for a in audits]

# Export endpoints with **lazy imports** to avoid startup crashes if optional deps are missing
@router.post("/export/png")
async def export_png(category_scores: dict = Body(None)):
    from ..audit.record import render_dashboard_png
    path = render_dashboard_png(category_scores)
    return FileResponse(path=str(path), filename=path.name, media_type="image/png")

@router.post("/export/ppt")
async def export_pptx(payload: dict = Body({})):
    from ..audit.record import export_ppt
    path = export_ppt(payload)
    media = "application/vnd.openxmlformats-officedocument.presentationml.presentation" if str(path).endswith(".pptx") else "image/png"
    return FileResponse(path=str(path), filename=path.name, media_type=media)

@router.post("/export/xlsx")
async def export_xlsx_file(payload: dict = Body({})):
    from ..audit.record import export_xlsx
    path = export_xlsx(payload)
    media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if str(path).endswith(".xlsx") else "image/png"
    return FileResponse(path=str(path), filename=path.name, media_type=media)
