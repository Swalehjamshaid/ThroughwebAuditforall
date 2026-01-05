import os
import hashlib
import hmac
import time
import jwt  # Requires PyJWT available in your environment

JWT_SECRET = os.getenv('JWT_SECRET', 'change-me-please')
JWT_ALGO   = os.getenv('JWT_ALGO', 'HS256')

# --- Password hashing (PBKDF2-HMAC-SHA256) ---
SALT = os.getenv('AUTH_SALT', 'fftech_salt').encode()
ITERATIONS = int(os.getenv('AUTH_ITERATIONS', '200000'))

def hash_password(plain: str) -> str:
    """Return a deterministic PBKDF2-HMAC-SHA256 hash string."""
    dk = hashlib.pbkdf2_hmac('sha256', plain.encode(), SALT, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${dk.hex()}"

def verify_password(plain: str, stored: str) -> bool:
    try:
        method, iterations_str, hex_hash = stored.split('$')
        assert method == 'pbkdf2_sha256'
        iterations = int(iterations_str)
        test = hashlib.pbkdf2_hmac('sha256', plain.encode(), SALT, iterations)
        return hmac.compare_digest(test.hex(), hex_hash)
    except Exception:
        return False

# --- JWT helpers ---

def create_token(payload: dict, expires_minutes: int = 60) -> str:
    now = int(time.time())
    exp = now + expires_minutes * 60
    to_encode = dict(payload)
    to_encode.update({'iat': now, 'exp': exp})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGO)

def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
