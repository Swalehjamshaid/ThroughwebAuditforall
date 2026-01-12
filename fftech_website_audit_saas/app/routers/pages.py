
from __future__ import annotations
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from .auth import get_current_user, require_admin

router = APIRouter()

@router.get('/admin', response_class=HTMLResponse)
async def admin_page(request: Request, db: Session = Depends(get_db), user: User | None = Depends(get_current_user)):
    admin = require_admin(user)
    users = db.query(User).order_by(User.id.asc()).all()
    rows = [{'name': u.email.split('@')[0].title(), 'email': u.email, 'role': ('Admin' if u.is_admin else 'User'), 'active': True} for u in users]
    return request.app.state.templates.TemplateResponse('admin.html', {'request': request, 'users': rows, 'year': request.app.state.year})
