
import time
import jwt
from typing import Optional, Dict
from app.core.config import settings

ALGORITHM = "HS256"

def create_jwt_token(user_id: int, role: str) -> str:
    now = int(time.time())
    exp = now + settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    payload = {"sub": str(user_id), "role": role, "iat": now, "exp": exp}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)

def decode_jwt_token(token: str) -> Optional[Dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
