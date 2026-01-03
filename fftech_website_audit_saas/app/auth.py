import uuid, datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt, JWTError
from passlib.hash import argon2
from sqlalchemy.orm import Session
from .config import SECRET_KEY, JWT_ALG
from .database import SessionLocal
from .models import User, EmailVerificationToken, Subscription
from .schemas import RegisterPayload

router = APIRouter(prefix="/auth", tags=["auth"])

# Dependency

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_jwt(user_id: int) -> str:
    payload = {"sub": str(user_id), "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=12)}
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALG)


def get_user_id_from_token(token: str, db: Session) -> int:
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALG])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    u = db.query(User).filter(User.id == int(data["sub"])) .first()
    if not u or not u.email_verified:
        raise HTTPException(status_code=401, detail="Email not verified")
    return u.id


def send_verification_email(to_email: str, token: str):
    verify_link = f"https://your-domain.com/auth/verify?token={token}"
    # Replace with SMTP integration
    print(f"[EMAIL] To:{to_email} Subject:Verify your email Body:{verify_link}")


@router.post("/register")
def register(payload: RegisterPayload, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    u = User(email=payload.email, password_hash=argon2.hash(payload.password))
    db.add(u); db.commit(); db.refresh(u)

    tok = EmailVerificationToken(
        token=str(uuid.uuid4()), user_id=u.id,
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(days=1)
    )
    db.add(tok); db.commit()
    send_verification_email(u.email, tok.token)
    return {"message": "Registration started. Please verify via email link."}


@router.get("/verify")
def verify(token: str, db: Session = Depends(get_db)):
    t = db.query(EmailVerificationToken).filter(EmailVerificationToken.token == token).first()
    if not t or t.used or t.expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid/expired token")
    u = db.query(User).filter(User.id == t.user_id).first()
    u.email_verified = True; db.add(u)
    t.used = True; db.add(t)
    sub = Subscription(user_id=u.id, plan="free", status="active", quota_limit=10)
    db.add(sub)
    db.commit()
    return {"message": "Email verified. You can now login."}


@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == form_data.username).first()
    if not u or not argon2.verify(form_data.password, u.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not u.email_verified:
        raise HTTPException(status_code=401, detail="Email not verified")
    return {"access_token": create_jwt(u.id), "token_type": "bearer"}
