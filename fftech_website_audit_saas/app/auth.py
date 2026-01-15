from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import jwt
from .config import settings
from .database import get_db          # ← FIXED HERE (change this line to match your actual file)
from .models import MagicToken, User
from .email_utils import send_email

router = APIRouter(prefix='/auth', tags=['auth'])

class LoginRequest(BaseModel):
    email: EmailStr

@router.post('/login-link')
def send_login_link(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    if not settings.MAGIC_EMAIL_ENABLED:
        raise HTTPException(status_code=403, detail='Magic email disabled')
    
    exp = datetime.utcnow() + timedelta(minutes=30)
    token = jwt.encode({'email': payload.email, 'exp': exp}, settings.JWT_SECRET, algorithm='HS256')
    
    mt = MagicToken(email=payload.email, token=token, valid_until=exp)
    db.add(mt)
    db.commit()
    
    link = f"{settings.BASE_URL}/auth/callback?token={token}"
    html = f"<p>Login to <b>{settings.UI_BRAND_NAME} Audit</b></p><p><a href='{link}'>Click here to sign in</a> (valid 30 minutes)</p>"
    
    try:
        send_email(to=payload.email, subject='Your secure login link', html=html)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Email send failed: {e}')
    
    return {'ok': True, 'message': 'Login link sent'}

@router.get('/callback')
def magic_callback(token: str, db: Session = Depends(get_db)):
    try:
        data = jwt.decode(token, settings.JWT_SECRET, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail='Token expired')
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail='Invalid token')
    
    mt = db.query(MagicToken).filter(MagicToken.token == token, MagicToken.used == False).first()
    if not mt or mt.valid_until < datetime.utcnow():
        raise HTTPException(status_code=400, detail='Token not valid')
    
    user = db.query(User).filter(User.email == data['email']).first()
    if not user:
        user = User(email=data['email'])
        db.add(user)
        db.commit()
        db.refresh(user)
    
    mt.used = True
    db.commit()
    
    session_token = jwt.encode(
        {'uid': user.id, 'email': user.email, 'iat': datetime.utcnow()},
        settings.JWT_SECRET,
        algorithm='HS256'
    )
    
    return {
        'ok': True,
        'token': session_token,
        'user': {
            'id': user.id,
            'email': user.email,
            'subscriber': user.is_subscriber
        }
    }
