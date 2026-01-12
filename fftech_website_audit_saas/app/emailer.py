
from __future__ import annotations
from typing import Optional
from .config import RESEND_API_KEY, DEFAULT_FROM_EMAIL
try:
    import resend
except Exception:
    resend = None

def send_magic_link(to: str, link: str, from_email: Optional[str] = None) -> dict:
    if not resend or not RESEND_API_KEY:
        return {"status": "disabled", "reason": "Resend not configured"}
    try:
        resend.api_key = RESEND_API_KEY
        html = f"<p>Click to sign in:</p><p><a href='{link}'>Sign in</a></p>"
        payload = {
            "from": from_email or DEFAULT_FROM_EMAIL,
            "to": [to],
            "subject": "Your secure sign-in link",
            "html": html,
        }
        return resend.Emails.send(payload)  # type: ignore[attr-defined]
    except Exception as exc:
        return {"status": "error", "reason": str(exc)}
