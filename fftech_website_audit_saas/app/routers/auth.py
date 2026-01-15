
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.orm import Session
from ..config import settings
from ..db import SessionLocal
from ..models import User
from ..email_utils import send_email

router = APIRouter()

SECRET = settings.SECRET_KEY
ser = URLSafeTimedSerializer(SECRET)


def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()


def set_session(resp, email: str):
    token = ser.dumps({'email': email})
    resp.set_cookie('session', token, httponly=True, samesite='lax', max_age=30*24*3600)


def get_user_from_cookie(request: Request, db: Session):
    token = request.cookies.get('session')
    if not token: return None
    try:
        data = ser.loads(token, max_age=30*24*3600)
        email = data.get('email')
        return db.query(User).filter(User.email==email).first()
    except Exception:
        return None

@router.get('/logout')
async def logout():
    resp = RedirectResponse('/')
    resp.delete_cookie('session')
    return resp

@router.post('/request-link')
async def request_link(payload: dict, db: Session = Depends(get_db)):
    email = payload.get('email')
    if not email: raise HTTPException(400, 'email required')
    token = ser.dumps(email)
    link = f"{settings.BASE_URL}/verify?token={token}"
    send_email(email, f"{settings.BRAND_NAME} Sign-in Link", f"Click to sign in: <a href='{link}'>Sign in</a>")
    return {'message':'Check your email for the sign-in link.'}

@router.get('/verify')
async def verify(request: Request, token: str, db: Session = Depends(get_db)):
    try:
        email = ser.loads(token, max_age=3600)
    except SignatureExpired:
        raise HTTPException(400, 'link expired')
    except BadSignature:
        raise HTTPException(400, 'invalid token')

    user = db.query(User).filter(User.email==email).first()
    if not user:
        user = User(email=email, is_verified=True)
        db.add(user); db.commit(); db.refresh(user)
    else:
        user.is_verified = True; db.commit()

    resp = RedirectResponse('/dashboard')
    set_session(resp, email)
    return resp
