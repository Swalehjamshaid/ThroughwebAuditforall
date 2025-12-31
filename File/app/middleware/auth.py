
from fastapi import Request
from app.db.session import SessionLocal
from app.db.models import MagicLinkToken
from app.core.security import decode_jwt_token
from datetime import datetime

async def auth_middleware(request: Request, call_next):
    auth = request.headers.get("Authorization")
    user_id = None
    if auth:
        parts = auth.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
            payload = decode_jwt_token(token)
            if payload:
                try:
                    user_id = int(payload.get("sub", 0))
                except Exception:
                    user_id = None
            else:
                db = SessionLocal()
                try:
                    row = db.query(MagicLinkToken).filter(MagicLinkToken.token == token).first()
                    if row and row.expires_at > datetime.utcnow():
                        user_id = row.user_id
                finally:
                    db.close()
    request.state.user_id = user_id
    response = await call_next(request)
    return response
