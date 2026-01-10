
from __future__ import annotations
from typing import Optional
from sqlalchemy.orm import Session
from passlib.hash import bcrypt
from .models import User

# Password hashing wrappers

def hash_password(password: str) -> str:
    return bcrypt.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.verify(password, hashed)
    except Exception:
        return False

# CRUD

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


def create_user(db: Session, email: str, password: str, name: Optional[str] = None, is_admin: bool = False) -> User:
    user = User(email=email.lower().strip(), name=name or email.split('@')[0], hashed_password=hash_password(password), is_admin=is_admin)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
