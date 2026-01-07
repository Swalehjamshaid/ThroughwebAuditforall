import os, time, json, hmac, hashlib, base64, secrets

SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')

# Simple salted SHA256 hash (demo). Use bcrypt/argon2 in production.
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return f"{salt}${digest}"

def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split('$', 1)
    except ValueError:
        return False
    check = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return hmac.compare_digest(check, digest)

# Minimal HMAC token
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')

def _b64url_decode(s: str) -> bytes:
    padding = '=' * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(s + padding)

def create_token(payload: dict, expires_minutes: int = 60) -> str:
    data = dict(payload)
    data['exp'] = int(time.time()) + (expires_minutes * 60)
    body = json.dumps(data, separators=(',', ':')).encode('utf-8')
    sig = hmac.new(SECRET_KEY.encode('utf-8'), body, hashlib.sha256).digest()
    return _b64url(body) + '.' + _b64url(sig)

def decode_token(token: str) -> dict:
    body_b64, sig_b64 = token.split('.', 1)
    body = _b64url_decode(body_b64)
    expected_sig = hmac.new(SECRET_KEY.encode('utf-8'), body, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_sig, _b64url_decode(sig_b64)):
        raise ValueError('bad-signature')
    data = json.loads(body.decode('utf-8'))
    if int(time.time()) > int(data.get('exp', 0)):
        raise ValueError('expired')
    return data
