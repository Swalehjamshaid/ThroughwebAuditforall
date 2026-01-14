
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import jwt
import resend

from app.config import settings
from app.database import db_session
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])
resend.api_key = settings.RESEND_API_KEY

class LoginRequest(BaseModel):
    email: EmailStr

@router.post("/login")
async def login(payload: LoginRequest, db: Session = Depends(db_session)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        user = User(email=payload.email, audit_count=0)
        db.add(user); db.commit(); db.refresh(user)

    exp = datetime.now(timezone.utc) + timedelta(minutes=30)
    token = jwt.encode({"sub": user.email, "exp": exp}, settings.JWT_SECRET, algorithm="HS256")
    magic_link = f"{settings.BASE_URL}/auth/callback?token={token}"

    try:
        resend.Emails.send({
            "from": settings.RESEND_FROM_EMAIL,
            "to": user.email,
            "subject": f"Login to {settings.UI_BRAND_NAME}",
            "html": f"<p>Login here: <a href='{magic_link}'>{magic_link}</a></p>"
        })
        return {"message": "Magic link sent"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/callback")
async def callback(token: str):
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return {"status": "success", "email": payload["sub"], "token": token}
    except jwt.PyJWTError:
        raise HTTPException(status_code=400, detail="Invalid token")
