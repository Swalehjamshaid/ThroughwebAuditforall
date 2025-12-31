
from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta, timezone
from .settings import settings
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_jwt(payload: dict, expires_minutes: int = 120) -> str:
    to_encode = payload.copy()
    to_encode.update({"exp": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")

def decode_jwt(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except Exception:
        return None
