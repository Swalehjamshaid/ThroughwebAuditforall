
import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.orm import Session
from .db import SessionLocal
from .models import User
from .email_utils import send_email

SECRET_KEY = os.getenv('SECRET_KEY', 'change-me')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')
serializer = URLSafeTimedSerializer(SECRET_KEY)
router = APIRouter()

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
    link = f"{BASE_URL}/verify?token={token}"
    send_email(email, 'FF Tech sign-in link', f"Click to sign in: <a href='{link}'>Sign in</a>")
    return {"message": "Check your email for the sign-in link."}

@router.get('/verify-token')
async def verify_token(token: str):
    try:
        email = serializer.loads(token, max_age=3600)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail='Link expired')
    except BadSignature:
        raise HTTPException(status_code=400, detail='Invalid token')
    # For API usage, just return email (front-end stores session)
    return {"email": email}
