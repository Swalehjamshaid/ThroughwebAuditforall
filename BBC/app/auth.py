from fastapi import APIRouter, Depends, HTTPException, Response, Request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.orm import Session
import smtplib
from email.message import EmailMessage
from .config import get_settings
from .database import get_db
from .models import User
import secrets

router = APIRouter(prefix='/api/auth', tags=['auth'])
settings = get_settings()

def _serializer():
    return URLSafeTimedSerializer(settings.SECRET_KEY, salt='magic-login')

def send_magic_email(email: str, token: str):
    if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD, settings.SMTP_FROM]):
        print(f"[DEV] Magic link for {email}: {settings.BASE_URL}/api/auth/verify?token={token}")
        return
    msg = EmailMessage(); msg['Subject']='Your FF Tech Audit Login Link'; msg['From']=settings.SMTP_FROM; msg['To']=email
    link = f"{settings.BASE_URL}/api/auth/verify?token={token}"
    msg.set_content(f"Click to login: {link}
This link expires in 30 minutes.")
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as s:
        s.starttls(); s.login(settings.SMTP_USER, settings.SMTP_PASSWORD); s.send_message(msg)

@router.post('/request-link')
async def request_link(payload: dict, db: Session = Depends(get_db)):
    email = payload.get('email','').strip().lower()
    if not email: raise HTTPException(status_code=400, detail='Email required')
    token = _serializer().dumps({'email': email})
    send_magic_email(email, token)
    return {"message":"If the email exists, a login link has been sent."}

@router.get('/verify')
async def verify(token: str, response: Response, db: Session = Depends(get_db)):
    try:
        data = _serializer().loads(token, max_age=1800)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail='Link expired')
    except BadSignature:
        raise HTTPException(status_code=400, detail='Invalid token')
    email = data['email']
    user = db.query(User).filter_by(email=email).first()
    if not user:
        user = User(email=email); db.add(user); db.commit()
    session_token = secrets.token_urlsafe(32)
    response.set_cookie('session', session_token, httponly=True, samesite='lax')
    return {"message":"Logged in","email":email}
