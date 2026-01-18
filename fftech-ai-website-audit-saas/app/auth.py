
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import jwt
from .config import settings
from .schemas import RequestLink
from .db import get_db
from .models import User
from .emailer import send_email

router = APIRouter(prefix="/api/auth", tags=["auth"])

JWT_ALG = "HS256"

@router.post('/request-link')
def request_link(payload: RequestLink, db: Session = Depends(get_db)):
    email = payload.email.lower()
    token = jwt.encode({
        'email': email,
        'exp': datetime.utcnow() + timedelta(minutes=20)
    }, settings.SECRET_KEY, algorithm=JWT_ALG)

    verify_url = f"{settings.BASE_URL}/api/auth/verify?token={token}"
    html = f"""
    <p>Click to sign in to FF Tech AI Audit:</p>
    <p><a href='{verify_url}'>Sign in</a></p>
    <p>This link expires in 20 minutes.</p>
    """
    send_email(email, "Your secure sign-in link", html)
    return {"message": "If the email exists, a sign-in link has been sent."}

@router.get('/verify')
def verify(token: str, response: Response, db: Session = Depends(get_db)):
    try:
        data = jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALG])
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    email = data['email'].lower()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email)
        db.add(user)
        db.commit()
        db.refresh(user)
    # Issue a session cookie (simple signed JWT)
    session_token = jwt.encode({'sub': str(user.id), 'exp': datetime.utcnow() + timedelta(days=7)}, settings.SECRET_KEY, algorithm=JWT_ALG)
    response = RedirectResponse(url='/dashboard')
    response.set_cookie(key='session', value=session_token, httponly=True, secure=True, samesite='lax')
    return response
