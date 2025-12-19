from fastapi import APIRouter, Depends, HTTPException
from ..db import session_scope
from ..models import User, AuditJob, AuditRun
from ..auth import decode_jwt

router = APIRouter(prefix='/admin', tags=['admin'])


def require_admin(token: str):
    payload = decode_jwt(token)
    if payload.get('role') != 'admin':
        raise HTTPException(status_code=403, detail='Admin only')
    return payload

@router.get('/users')
def list_users(authorization: str):
    payload = require_admin(authorization.replace('Bearer ', ''))
    with session_scope() as s:
        users = s.query(User).all()
        return [{"id": u.id, "email": u.email, "role": u.role, "verified": u.email_verified} for u in users]

@router.get('/audits')
def list_audits(authorization: str):
    payload = require_admin(authorization.replace('Bearer ', ''))
    with session_scope() as s:
        jobs = s.query(AuditJob).all()
        return [{"id": j.id, "url": j.target_url, "active": j.active} for j in jobs]
