
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from ..db import db_session
from ..models import User, Audit

router = APIRouter(prefix='/user', tags=['user'])

@router.get('/dashboard', response_class=HTMLResponse)
def dashboard(request: Request, email: str, db: Session = Depends(db_session)):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory='app/templates')
    user = db.query(User).filter(User.email==email).first()
    audits = []
    if user:
        audits = db.query(Audit).filter(Audit.user_id==user.id).order_by(Audit.created_at.desc()).all()
    return templates.TemplateResponse('dashboard.html', {'request': request, 'user': user, 'audits': audits})
