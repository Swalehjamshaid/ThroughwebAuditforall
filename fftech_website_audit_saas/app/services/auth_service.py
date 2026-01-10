
"""Passwordless email auth using signed tokens (magic link).
Production: integrate real email provider (SendGrid/Postmark) and DB storage.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional
import os

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired  # type: ignore

SECRET = os.getenv('AUTH_SECRET', 'dev-secret')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')
TOKEN_MAX_AGE = int(os.getenv('TOKEN_MAX_AGE', '1800'))  # 30 min

serializer = URLSafeTimedSerializer(SECRET)


def create_login_token(email: str) -> str:
    return serializer.dumps({'email': email})


def verify_login_token(token: str) -> Optional[str]:
    try:
        data = serializer.loads(token, max_age=TOKEN_MAX_AGE)
        return data.get('email')
    except SignatureExpired:
        return None
    except BadSignature:
        return None


def build_magic_link(token: str) -> str:
    return f"{BASE_URL}/verify?token={token}"

