
from __future__ import annotations
import uuid
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime

from .services.config import setup_logging, APP_BASE_URL
from .services.db import SessionLocal, engine
from .models import Base, User
from .email_utils import send_magic_link

logger, _ = setup_logging()
router = APIRouter()

Base.metadata.create_all(bind=engine)

@router.get('/login', response_class=HTMLResponse)
async def login_page(request: Request):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory=str((request.app).templates.directory))
    return templates.TemplateResponse('login.html', {'request': request, 'title': 'Login'})

@router.post('/login', response_class=HTMLResponse)
async def login_submit(request: Request, email: str = Form(...)):
    token = str(uuid.uuid4())
    with SessionLocal() as session:
        user = session.query(User).filter(User.email == email).one_or_none()
        if not user:
            user = User(email=email, token=token, verified=False, created_at=datetime.utcnow())
            session.add(user)
        else:
            user.token = token
        session.commit()
    verify_link = f"{APP_BASE_URL}/verify?token={token}&email={email}"
    send_magic_link(email, verify_link, logger)
    return RedirectResponse(url='/verify?sent=1', status_code=303)

@router.get('/verify', response_class=HTMLResponse)
async def verify(request: Request, token: str | None = None, email: str | None = None, sent: int | None = None):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory=str((request.app).templates.directory))
    if sent:
        return templates.TemplateResponse('verify.html', {'request': request, 'title': 'Verify', 'message': 'Check your email for the login link.'})
    if not token or not email:
        return templates.TemplateResponse('verify.html', {'request': request, 'title': 'Verify', 'message': 'Missing token/email.'})
    with SessionLocal() as session:
        user = session.query(User).filter(User.email == email).one_or_none()
        if user and user.token == token:
            user.verified = True
            user.token = None
            session.commit()
            resp = RedirectResponse(url='/dashboard', status_code=303)
            resp.set_cookie('user_email', email, httponly=True)
            return resp
    return templates.TemplateResponse('verify.html', {'request': request, 'title': 'Verify', 'message': 'Invalid or expired token.'})

@router.get('/logout')
async def logout():
    resp = RedirectResponse(url='/', status_code=303)
    resp.delete_cookie('user_email')
    return resp

