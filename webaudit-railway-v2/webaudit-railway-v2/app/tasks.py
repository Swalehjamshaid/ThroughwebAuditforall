import os
from datetime import datetime
from celery import Celery
from .lighthouse_runner import run_lighthouse
from .audit_service import consolidate_45_plus_metrics
from .email import send_audit_email
from .models import db, Website, Audit
from . import create_app

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery = Celery(__name__, broker=REDIS_URL, backend=REDIS_URL)
celery.conf.timezone = os.getenv("TZ", "UTC")

flask_app = create_app()

@celery.task(name="app.tasks.run_lighthouse_audit")
def run_lighthouse_audit(website_id, url, form_factor="desktop"):
    with flask_app.app_context():
        audit = Audit(website_id=website_id, started_at=datetime.utcnow(), status="running")
        db.session.add(audit); db.session.commit()
        try:
            lhr = run_lighthouse(url, form_factor=form_factor)
            cats = lhr.get("categories", {})
            def score(cat):
                s = cats.get(cat, {}).get("score")
                return round(float(s)*100, 2) if s is not None else None
            metrics = consolidate_45_plus_metrics(url)
            audit.lighthouse_json = lhr
            audit.metrics_json = metrics
            audit.score_perf = score("performance")
            audit.score_accessibility = score("accessibility")
            audit.score_best_practices = score("best-practices")
            audit.score_seo = score("seo")
            audit.score_pwa = score("pwa")
            parts = [audit.score_perf, audit.score_accessibility, audit.score_best_practices, audit.score_seo]
            parts = [p for p in parts if p is not None]
            audit.score_overall = round(sum(parts)/len(parts), 2) if parts else None
            audit.status = "completed"
            audit.finished_at = datetime.utcnow()
            db.session.commit()
            send_audit_email(website_id, audit.id)
            return {"audit_id": audit.id, "overall": audit.score_overall}
        except Exception as e:
            audit.status = "failed"
            audit.finished_at = datetime.utcnow()
            db.session.commit()
            raise e

@celery.task(name="app.tasks.run_scheduled_audits")
def run_scheduled_audits():
    with flask_app.app_context():
        for w in Website.query.all():
            run_lighthouse_audit.delay(w.id, w.url)
