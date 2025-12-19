import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from .lighthouse_runner import run_lighthouse
from ..reporting.grading import grade_from_score
from ..reporting.pdf_report import generate_pdf
from ..db import session_scope
from ..models import AuditJob, AuditRun, CertifiedReport

scheduler = BackgroundScheduler(timezone=os.getenv('DEFAULT_TIMEZONE', 'UTC'))


def compute_score_from_lh(lh: dict) -> float:
    # Aggregate categories as a simple average of category scores (0-1)
    cats = lh.get('categories', {})
    scores = [cats[c]['score'] for c in cats if cats[c].get('score') is not None]
    if not scores:
        return 0.0
    return sum(scores) / len(scores) * 100.0


def run_audit_for_job(job_id: int):
    with session_scope() as s:
        job = s.get(AuditJob, job_id)
        if not job or not job.active:
            return
        run = AuditRun(job_id=job.id, status='pending', started_at=datetime.utcnow())
        s.add(run)
        s.flush()
        try:
            lh = run_lighthouse(job.target_url)
            score = compute_score_from_lh(lh)
            grade = grade_from_score(score)
            run.lighthouse_report = lh
            run.metrics_summary = {'overall_score': score}
            run.score = score
            run.grade = grade
            run.status = 'success'
            run.finished_at = datetime.utcnow()
            # Create PDF report
            pdf_path = f"/app/reports/report_{run.id}.pdf"
            os.makedirs('/app/reports', exist_ok=True)
            generate_pdf(pdf_path, job.target_url, grade, score, {'overall_score': f"{score:.1f}"})
            s.add(CertifiedReport(run_id=run.id, pdf_path=pdf_path))
        except Exception as e:
            run.status = 'failed'
            run.finished_at = datetime.utcnow()
            run.metrics_summary = {'error': str(e)}


def schedule_daily(job: AuditJob, hour: int, minute: int):
    scheduler.add_job(run_audit_for_job, CronTrigger(hour=hour, minute=minute), args=[job.id], id=f"audit-{job.id}")


def start_scheduler():
    scheduler.start()
