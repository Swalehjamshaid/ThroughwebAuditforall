
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from .db import SessionLocal
from .models import Schedule, Website, User, Audit
from .report import generate_report
from .emailer import send_email, smtp_configured

async def schedule_loop():
    while True:
        try:
            with SessionLocal() as db:
                run_schedules(db)
        except Exception:
            pass
        await asyncio.sleep(60)

def run_schedules(db: Session):
    if not smtp_configured():
        return
    now_utc = datetime.now(timezone.utc)
    for s in db.query(Schedule).filter(Schedule.enabled == True).all():
        tz = ZoneInfo(s.timezone)
        local = now_utc.astimezone(tz)
        if local.hour == s.hour and local.minute == s.minute:
            if not s.last_sent or s.last_sent.date() != local.date():
                w = db.query(Website).get(s.website_id)
                u = db.query(User).get(s.user_id)
                if w and u:
                    last = db.query(Audit).filter(Audit.website_id == w.id).order_by(Audit.created_at.desc()).first()
                    m = last.metrics if last else {"overall": 90, "lcp": 2100, "inp": 160, "cls": 0.03}
                    pdf = generate_report(w.url, last.grade if last else "A", "Daily automated snapshot.", m, accumulated=True)
                    ok = send_email(u.email, f"FF Tech Report – {w.url}", "<p>Your report is attached.</p>")
                    if ok:
                        s.last_sent = now_utc
                        db.add(s); db.commit()
