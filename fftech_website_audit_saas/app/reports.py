from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from .db import SessionLocal
from .models import Audit

router = APIRouter()

@router.get('/reports/pdf/{audit_id}')
async def pdf(audit_id: int):
    db = SessionLocal()
    try:
        a = db.query(Audit).filter(Audit.id==audit_id).first()
        if not a or not a.report_pdf_path:
            raise HTTPException(status_code=404, detail='Report not found')
        return FileResponse(a.report_pdf_path, media_type='application/pdf', filename=f'audit_{audit_id}.pdf')
    finally:
        db.close()