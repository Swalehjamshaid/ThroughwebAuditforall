from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import jwt, resend
from ..config import settings
from ..db import db_session
from ..models import MagicToken, User

router = APIRouter(prefix='/auth', tags=['auth'])
resend.api_key = settings.RESEND_API_KEY # Key from image_18abc1.png

class MagicLinkRequest(BaseModel):
    email: EmailStr

@router.post('/login-link')
def send_link(payload: MagicLinkRequest, db: Session = Depends(db_session)):
    exp = datetime.now(timezone.utc) + timedelta(minutes=30)
    token = jwt.encode({'email': payload.email, 'exp': exp.timestamp()}, settings.JWT_SECRET)
    
    db.add(MagicToken(email=payload.email, token=token, valid_until=exp))
    db.commit()

    link = f"{settings.BASE_URL}/auth/callback?token={token}"
    
    resend.Emails.send({
        "from": settings.RESEND_FROM_EMAIL,
        "to": payload.email,
        "subject": f"Login to {settings.UI_BRAND_NAME}",
        "html": f"<strong>FF Tech AI Audit</strong><br><br><a href='{link}'>Click here to sign in</a>"
    })
    return {"message": "Magic link sent"}

@router.get('/callback')
def callback(token: str, db: Session = Depends(db_session)):
    try:
        data = jwt.decode(token, settings.JWT_SECRET, algorithms=['HS256'])
        email = data['email']
    except:
        raise HTTPException(status_code=400, detail="Expired or invalid link")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email)
        db.add(user)
    db.commit()
    
    session = jwt.encode({'uid': user.id, 'email': user.email}, settings.JWT_SECRET)
    return {"token": session, "email": email}
