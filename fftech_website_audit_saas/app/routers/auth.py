
from __future__ import annotations
from datetime import datetime, timedelta
import jwt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import User
from ..config import SECRET_KEY, JWT_ALGORITHM, BACKEND_BASE_URL
from ..emailer import send_magic_link

router = APIRouter(prefix="/auth", tags=["auth"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/request-link")
async def request_link(email: str):
    payload = {"sub": email, "purpose": "magic", "exp": int((datetime.utcnow() + timedelta(minutes=15)).timestamp())}
    token = jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)
    link = f"{BACKEND_BASE_URL}/auth/magic?token={token}"
    result = send_magic_link(email, link)
    return {"status": "sent", "provider": result.get("status", "ok")}

@router.get("/magic")
async def magic(token: str, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get("purpose") != "magic":
            raise HTTPException(status_code=400, detail="Invalid token purpose")
        email = payload.get("sub")
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email, email_verified=True)
            db.add(user)
        else:
            user.email_verified = True
        db.commit()
        api_payload = {"sub": email, "iat": int(datetime.utcnow().timestamp())}
        api_token = jwt.encode(api_payload, SECRET_KEY, algorithm=JWT_ALGORITHM)
        return {"status": "ok", "token": api_token}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid or expired token: {exc}")
