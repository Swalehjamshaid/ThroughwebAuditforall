from fastapi import APIRouter, HTTPException
from .db import SessionLocal
from .models import Schedule, User

router = APIRouter()

@router.post('/schedule')
async def create_schedule(payload: dict, x_user_email: str | None = None):
    if not x_user_email:
        raise HTTPException(status_code=401, detail='Sign in required')
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email==x_user_email).first()
        if not user:
            raise HTTPException(status_code=401, detail='Invalid user')
        if user.subscription == 'free':
            raise HTTPException(status_code=402, detail='Scheduling is paid feature. Upgrade to enable.')
        s = Schedule(user_id=user.id, url=payload.get('url'), cron=payload.get('cron'), active=True)
        db.add(s)
        db.commit()
        db.refresh(s)
        return {'id': s.id, 'status':'scheduled'}
    finally:
        db.close()