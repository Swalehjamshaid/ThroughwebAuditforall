from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.orm import Session
from .config import settings
from .db import SessionLocal
from .models import User
from .email_utils import send_email

router = APIRouter()
serializer = URLSafeTimedSerializer(settings.SECRET_KEY)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post('/request-link')
async def request_link(payload: dict):
    email = payload.get('email')
    if not email:
        raise HTTPException(status_code=400, detail='email required')
    token = serializer.dumps(email)
    link = f"{settings.BASE_URL}/api/auth/verify?token={token}"
    send_email(email, f"{settings.BRAND_NAME} Sign-in", f"Click to sign in: <a href='{link}'>Sign in</a>")
    return {"message": "Check your email for the sign-in link."}

@router.get('/verify')
async def verify(token: str):
    try:
        email = serializer.loads(token, max_age=3600)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail='Link expired')
    except BadSignature:
        raise HTTPException(status_code=400, detail='Invalid token')

    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email, is_verified=True)
            db.add(user)
            db.commit()
        else:
            user.is_verified = True
            db.commit()
    finally:
        db.close()

    return RedirectResponse(url=f"/?signed_in=1&email={email}")