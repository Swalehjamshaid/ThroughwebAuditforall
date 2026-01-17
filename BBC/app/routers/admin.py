from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, AuditJob, AuditResult, MonitoredTarget
from ..config import get_settings

router = APIRouter(prefix='/admin', tags=['admin'])

def _guard(req: Request):
    token = req.headers.get('X-Admin-Token')
    if not token or token != get_settings().ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail='Admin token required')

@router.get('/overview')
async def overview(req: Request, db: Session = Depends(get_db)):
    _guard(req)
    return {
        'users': db.query(User).count(),
        'audits': db.query(AuditJob).count(),
        'results': db.query(AuditResult).count(),
        'monitored_targets': db.query(MonitoredTarget).count(),
    }
