
from flask_apscheduler import APScheduler

scheduler = APScheduler()

def init_scheduler(app):
    app.config["SCHEDULER_API_ENABLED"] = True
    scheduler.init_app(app)

    @scheduler.task("cron", id="nightly_audits", hour=3)
    def nightly_audits():
        from .models import Website
        from .tasks import run_lighthouse_audit
        for w in Website.query.all():
            run_lighthouse_audit.delay(w.id, w.url)

    scheduler.start()
