# fftech_audit/auth_email.py
import os
import time
import hmac
import base64
import hashlib
from typing import Tuple, Optional

_SECRET = (os.getenv("TOKEN_SECRET") or "change-me-to-a-long-random-secret").encode("utf-8")

def _sign(payload: str) -> str:
    sig = hmac.new(_SECRET, payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")

def _now_ts() -> int:
    return int(time.time())

class verify_token:
    @staticmethod
    def issue(email: str, ttl_seconds: int = 900) -> str:
        exp = _now_ts() + ttl_seconds
        payload = f"{email}|{exp}"
        sig = _sign(payload)
        token = base64.urlsafe_b64encode(f"{payload}|{sig}".encode("utf-8")).decode("utf-8").rstrip("=")
        return token

    @staticmethod
    def check(token: str) -> Tuple[bool, Optional[str]]:
        try:
            raw = base64.urlsafe_b64decode(token + "==").decode("utf-8")
            email, exp_s, sig = raw.split("|")
            payload = f"{email}|{exp_s}"
            if _sign(payload) != sig:
                return False, None
            if _now_ts() > int(exp_s):
                return False, None
            return True, email
        except Exception:
            return False, None


def send_magic_link_email(email: str, token: str):
    """
    Stub email sender. Replace with SMTP or provider integration (e.g., SendGrid).
    """
    # In production, build the Railway base URL dynamically from env
    base_url = os.getenv("APP_BASE_URL", "http://localhost:8000")
    link = f"{base_url}/verify?token={token}"
    print(f"[Magic Link] Send to {email}: {link}")
    # TODO: Implement real email send here for production
