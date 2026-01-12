
from __future__ import annotations
import os
from typing import Optional
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User, hash_password, verify_password

router = APIRouter()
SESSION_KEY = os.getenv('SESSION_KEY', 'fftech_session')

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    uid = request.session.get(SESSION_KEY)
    if not uid:
        return None
    return db.query(User).filter(User.id == uid).first()

def require_user(user: Optional[User]) -> User:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication required')
    return user

def require_admin(user: Optional[User]) -> User:
    if not user or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Admin required')
    return user

@router.get('/login', response_class=HTMLResponse)
async def login_page(request: Request):
    return request.app.state.templates.TemplateResponse('login.html', {'request': request, 'year': request.app.state.year})

@router.post('/login', response_class=HTMLResponse)
async def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.hashed_password or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid credentials')
    request.session[SESSION_KEY] = user.id
    return RedirectResponse(url='/', status_code=303)

@router.get('/register', response_class=HTMLResponse)
async def register_page(request: Request):
    return request.app.state.templates.TemplateResponse('register.html', {'request': request, 'year': request.app.state.year})

@router.post('/register')
async def register(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.email == email).first()
    if exists:
        return RedirectResponse(url='/login', status_code=303)
    user = User(email=email, hashed_password=None, is_admin=False)
    db.add(user); db.commit()
    return RedirectResponse(url='/verify', status_code=303)

@router.post('/logout')
async def logout(request: Request):
    request.session.pop(SESSION_KEY, None)
    return RedirectResponse(url='/', status_code=303)

# Admin seed
from sqlalchemy.orm import Session as _Session

def seed_admin(db: _Session):
    admin_email = os.getenv('ADMIN_EMAIL', 'roy.jamshaid@gmail.com')
    admin_password = os.getenv('ADMIN_PASSWORD', 'Jamshaid,1981')
    user = db.query(User).filter(User.email == admin_email).first()
    if not user:
        user = User(email=admin_email, hashed_password=hash_password(admin_password), is_admin=True)
        db.add(user); db.commit()
