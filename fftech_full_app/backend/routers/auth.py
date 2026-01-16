import os
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from ..database import SessionLocal
from ..models import User
from ..config import settings

router = APIRouter()
serializer = URLSafeTimedSerializer(settings.SECRET_KEY)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def send_email(to_email: str, subject: str, body: str):
    host = os.getenv('SMTP_HOST')
    user = os.getenv('SMTP_USER')
    password = os.getenv('SMTP_PASS')
    from_email = os.getenv('FROM_EMAIL', 'no-reply@fftech.ai')
    if not host or not user or not password:
        print('=== EMAIL (console) ===')
        print('TO:', to_email); print('SUBJECT:', subject); print(body)
        return
    import smtplib
    from email.mime.text import MIMEText
    msg = MIMEText(body, 'html'); msg['Subject']=subject; msg['From']=from_email; msg['To']=to_email
    with smtplib.SMTP(host, int(os.getenv('SMTP_PORT','587'))) as s:
        s.starttls(); s.login(user, password); s.sendmail(from_email, [to_email], msg.as_string())

@router.post('/api/auth/request-link')
async def request_link(payload: dict, db: Session = Depends(get_db)):
    email = payload.get('email')
    if not email:
        raise HTTPException(status_code=400, detail='email required')
    token = serializer.dumps(email)
    link = f"{settings.BASE_URL}/api/auth/verify?token={token}"
    send_email(email, f"{settings.BRAND_NAME} Sign-in Link", f"Click to sign in: <a href='{link}'>Sign in</a>")
    return {"message":"Email sent"}

@router.get('/api/auth/verify')
async def verify(token: str, db: Session = Depends(get_db)):
    try:
        email = serializer.loads(token, max_age=3600)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail='Link expired')
    except BadSignature:
        raise HTTPException(status_code=400, detail='Invalid token')
    user = db.query(User).filter(User.email==email).first()
    if not user:
        user = User(email=email, is_verified=True)
        db.add(user); db.commit(); db.refresh(user)
    else:
        user.is_verified = True; db.commit()
    return RedirectResponse(url=f"/verify?email={email}")