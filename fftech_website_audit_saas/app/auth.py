import os
from fastapi import APIRouter, HTTPException
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from .db import SessionLocal
from .models import User
from .email_utils import send_email

router = APIRouter()
serializer = URLSafeTimedSerializer(os.getenv('SECRET_KEY', 'change-me'))
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')
BRAND = os.getenv('BRAND_NAME', 'FF Tech')


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post('/request-link')
async def request_link(payload: dict):
    email = (payload or {}).get('email')
    if not email:
        raise HTTPException(status_code=400, detail='email required')
    token = serializer.dumps(email)
    link = f"{BASE_URL}/api/auth/verify?token={token}"
    send_email(email, f"{BRAND} Sign-in Link", f"Click to sign in: <a href='{link}'>Sign in</a>")
    return {"message": "Sign-in link sent"}

@router.get('/verify')
async def verify(token: str):
    try:
        email = serializer.loads(token, max_age=3600)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail='Link expired')
    except BadSignature:
        raise HTTPException(status_code=400, detail='Invalid token')

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email==email).first()
        if not user:
            user = User(email=email, is_verified=True)
            db.add(user)
            db.commit()
        else:
            user.is_verified = True
            db.commit()
    finally:
        db.close()

    # For demo, just redirect with a flag
    return RedirectResponse(url=f"/?signed_in=1&email={email}")