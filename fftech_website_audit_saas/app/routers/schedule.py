from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from ..database import SessionLocal
from .. import models
from ..schemas import ScheduleRequest

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post('/schedule')
async def create_schedule(payload: ScheduleRequest, db: Session = Depends(get_db), x_user_email: str | None = None):
    if not x_user_email:
        raise HTTPException(status_code=401, detail='Sign in required')
    user = db.query(models.User).filter(models.User.email == x_user_email).first()
    if not user:
        raise HTTPException(status_code=401, detail='Invalid user')
    if user.subscription == 'free':
        raise HTTPException(status_code=402, detail='Scheduling is paid feature. Upgrade to enable.')

    s = models.Schedule(user_id=user.id, url=payload.url, cron=payload.cron, active=True)
    db.add(s); db.commit(); db.refresh(s)
    return {"id": s.id, "status": "scheduled"}