import os, smtplib
from email.mime.text import MIMEText
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..config import settings
from ..database import SessionLocal
from .. import models

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

serializer = URLSafeTimedSerializer(settings.SECRET_KEY)

def send_email(to_email: str, subject: str, body: str):
    host = os.getenv('SMTP_HOST')
    user = os.getenv('SMTP_USER')
    password = os.getenv('SMTP_PASS')
    from_email = os.getenv('FROM_EMAIL', 'no-reply@fftech.ai')
    if not host or not user or not password:
        print("=== EMAIL (console) ===
TO:", to_email, "
SUBJECT:", subject, "
", body, "
=======================")
        return
    msg = MIMEText(body, 'html')
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = to_email
    with smtplib.SMTP(host, int(os.getenv('SMTP_PORT', '587'))) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(from_email, [to_email], msg.as_string())

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