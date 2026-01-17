from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from .database import SessionLocal
from .models import MonitoredTarget, AuditJob, AuditResult
from .audit.metrics import compute_metrics
from .audit.scoring import score_category, overall_score, letter_grade
from .audit.report import generate_pdf
import os

scheduler = BackgroundScheduler(timezone='UTC')

def _due(mt: MonitoredTarget) -> bool:
    if not mt.active: return False
    if not mt.last_run: return True
    delta = {'daily':1,'weekly':7,'monthly':30}.get(mt.cadence,7)
    return (datetime.utcnow() - mt.last_run) > timedelta(days=delta)


def job_scheduled_audits():
    db: Session = SessionLocal()
    try:
        targets = db.query(MonitoredTarget).all()
        for mt in targets:
            if not _due(mt): continue
            url = mt.url
            m = compute_metrics(url)
            s = score_category(m)
            overall = overall_score(s); grade = letter_grade(overall)
            out_dir = 'data/reports'; os.makedirs(out_dir, exist_ok=True)
            pdf_path = os.path.join(out_dir, f"scheduled_{grade}_{os.getpid()}.pdf")
            generate_pdf(pdf_path, url, m, s, overall, grade)
            job = AuditJob(user_id=mt.user_id, target_url=url, status='completed')
            db.add(job); db.commit(); db.refresh(job)
            res = AuditResult(job_id=job.id, metrics=m, scores={**s,'overall':overall,'grade':grade}, pdf_path=pdf_path)
            db.add(res); mt.last_run = datetime.utcnow(); db.commit()
    finally:
        db.close()


def start():
    scheduler.add_job(job_scheduled_audits, 'interval', minutes=30, id='scheduled_audits', replace_existing=True)
    scheduler.start()
