
from apscheduler.schedulers.background import BackgroundScheduler
from typing import Callable

scheduler = BackgroundScheduler()

def start():
    scheduler.start()

def add_recurring(job_id: str, func: Callable, minutes: int = 1440, **kwargs):
    scheduler.add_job(func, 'interval', minutes=minutes, id=job_id, replace_existing=True, kwargs=kwargs)
