
import os
import hashlib
import time
import jwt  # PyJWT

SECRET_KEY = os.getenv("SECRET_KEY", "fftech-secret-change-me")
ALGO       = "HS256"

def hash_password(raw: str) -> str:
    # Simple SHA256 hash; for production switch to bcrypt/argon2.
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def verify_password(raw: str, hashed: str) -> bool:
    return hash_password(raw) == hashed

def create_token(payload: dict, expires_minutes: int = 60) -> str:
    exp = int(time.time()) + (expires_minutes * 60)
    to_encode = {**payload, "exp": exp}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGO)

def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGO])
