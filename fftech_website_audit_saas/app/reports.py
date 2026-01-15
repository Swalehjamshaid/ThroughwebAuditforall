
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from .db import SessionLocal
from . import models

router = APIRouter()

@router.get('/reports/pdf/{audit_id}')
async def download_pdf(audit_id: int):
    db = SessionLocal()
    try:
        audit = db.query(models.Audit).filter(models.Audit.id == audit_id).first()
        if not audit or not audit.report_pdf_path:
            raise HTTPException(status_code=404, detail='Report not found')
        return FileResponse(audit.report_pdf_path, media_type='application/pdf', filename=f'audit_{audit_id}.pdf')
    finally:
        db.close()
