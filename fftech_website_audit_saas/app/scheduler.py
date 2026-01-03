import datetime
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from .database import SessionLocal
from .models import Website, Audit
from .audit_engine import run_basic_audit, strict_score, generate_summary_200

scheduler = BackgroundScheduler()
scheduler.start()

def schedule_daily_audit(user_timezone: str, job_id: str, hour_local: int, minute_local: int, website_id: int):
    tz = pytz.timezone(user_timezone or "UTC")
    trigger = CronTrigger(hour=hour_local, minute=minute_local, timezone=tz)
    scheduler.add_job(run_scheduled_audit, trigger, args=[website_id], id=job_id, replace_existing=True)


def run_scheduled_audit(website_id: int):
    db = SessionLocal()
    try:
        w = db.query(Website).filter(Website.id == website_id).first()
        if not w: return
        metrics = run_basic_audit(w.url)
        score, grade = strict_score(metrics)
        summary = generate_summary_200(metrics, score, grade)
        a = Audit(website_id=w.id, started_at=datetime.datetime.utcnow(), finished_at=datetime.datetime.utcnow(),
                  grade=grade, overall_score=score, summary_200_words=summary, json_metrics=metrics)
        db.add(a); db.commit()
        # TODO: send email with summary + link to report
    finally:
        db.close()
