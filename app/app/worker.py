from celery import Celery
import os, pytz
from .app import create_app, db
from .models import Organization
from datetime import datetime

app = create_app()
celery_app = Celery('tasks', broker=os.environ.get('REDIS_URL'))

@celery_app.task
def check_schedules():
    """The Watchman: Checks every minute for user demand"""
    with app.app_context():
        orgs = Organization.query.all()
        for org in orgs:
            user_tz = pytz.timezone(org.timezone)
            local_time = datetime.now(pytz.utc).astimezone(user_tz).strftime("%H:%M")
            if local_time == org.report_time:
                # Trigger Audit Task
                pass
