
import bcrypt
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from .config import settings
from .db import SessionLocal
from . import models
from .email_utils import send_email

router = APIRouter()

serializer = URLSafeTimedSerializer(settings.SECRET_KEY)

# DB dependency

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Cookie helpers
COOKIE_NAME = 'fftech_session'
COOKIE_MAX_AGE = 60*60*24*7  # 7 days

def set_session_cookie(response: Response, email: str, role: str = 'user'):
    token = serializer.dumps({'email': email, 'role': role})
    response.set_cookie(COOKIE_NAME, token, max_age=COOKIE_MAX_AGE, httponly=True, samesite='lax')

def read_session(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        data = serializer.loads(token, max_age=COOKIE_MAX_AGE)
        return data
    except Exception:
        return None

@router.post('/request-link')
async def request_link(payload: dict, db: Session = Depends(get_db)):
    email = payload.get('email')
    if not email:
        raise HTTPException(status_code=400, detail='email required')
    token = serializer.dumps(email)
    link = f"{settings.BASE_URL}/api/auth/verify?token={token}"
    send_email(email, f"{settings.BRAND_NAME} Sign-in Link", f"Click to sign in: <a href='{link}'>Sign in</a>")
    return {"message": "Check your email for the sign-in link."}

@router.get('/verify')
async def verify(token: str, response: Response, db: Session = Depends(get_db)):
    try:
        email = serializer.loads(token, max_age=3600)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail='Link expired')
    except BadSignature:
        raise HTTPException(status_code=400, detail='Invalid token')

    user = db.query(models.User).filter(models.User.email==email).first()
    if not user:
        user = models.User(email=email, is_verified=True, role='user')
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.is_verified = True
        db.commit()

    set_session_cookie(response, email=email, role=user.role)
    return RedirectResponse(url='/?signed_in=1')

@router.post('/login')
async def admin_login(payload: dict, response: Response, db: Session = Depends(get_db)):
    email = payload.get('email'); password = payload.get('password','')
    if not email or not password:
        raise HTTPException(status_code=400, detail='email and password required')
    user = db.query(models.User).filter(models.User.email==email).first()
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail='invalid credentials')
    if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail='invalid credentials')
    set_session_cookie(response, email=email, role=user.role)
    return {"message": "logged in"}

@router.post('/logout')
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"message": "logged out"}

# Utility to fetch current user from cookie
@router.get('/me')
async def me(request: Request):
    data = read_session(request)
    if not data:
        return {"authenticated": False}
    return {"authenticated": True, "email": data['email'], "role": data.get('role','user')}
