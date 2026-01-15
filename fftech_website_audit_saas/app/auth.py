
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from .db import SessionLocal
from .config import settings
from . import models
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
async def request_link(payload: dict, db: Session = Depends(get_db)):
    email = payload.get('email')
    if not email:
        raise HTTPException(status_code=400, detail='email required')
    token = serializer.dumps(email)
    link = f"{settings.BASE_URL}/api/auth/verify?token={token}"
    send_email(email, f"{settings.BRAND_NAME} Sign-in Link", f"Click to sign in: <a href='{link}'>Sign in</a>")
    return {"message": "Check your email for the sign-in link."}

@router.get('/verify')
async def verify(token: str, db: Session = Depends(get_db)):
    try:
        email = serializer.loads(token, max_age=3600)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail='Link expired')
    except BadSignature:
        raise HTTPException(status_code=400, detail='Invalid token')

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        user = models.User(email=email, is_verified=True)
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.is_verified = True
        db.commit()

    return RedirectResponse(url=f"/?signed_in=1&email={email}")
