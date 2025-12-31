
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from app.db.session import SessionLocal
from app.db.models import User, MagicLinkToken
from app.core.security import create_jwt_token
from datetime import datetime, timedelta
import secrets

router = APIRouter()

class SendLinkRequest(BaseModel):
    email: EmailStr

class VerifyRequest(BaseModel):
    token: str

@router.post("/send-link")
def send_link(payload: SendLinkRequest):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == payload.email).first()
        if not user:
            user = User(email=payload.email, created_at=datetime.utcnow())
            db.add(user)
            db.flush()
        token = secrets.token_hex(32)
        row = MagicLinkToken(
            token=token,
            email=payload.email,
            user_id=user.id,
            expires_at=datetime.utcnow() + timedelta(hours=12),
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        return {"status": "sent", "token": token}
    finally:
        db.close()

@router.post("/verify")
def verify(payload: VerifyRequest):
    db = SessionLocal()
    try:
        row = db.query(MagicLinkToken).filter(MagicLinkToken.token == payload.token).first()
        if not row or row.expires_at <= datetime.utcnow():
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        row.redeemed = True
        db.commit()
        user = db.query(User).filter(User.id == row.user_id).first()
        token_jwt = create_jwt_token(row.user_id, user.role)
        return {"status": "verified", "user_id": row.user_id, "access_token": token_jwt, "token_type": "bearer"}
    finally:
        db.close()
