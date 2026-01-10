
"""Simple scheduler stub. In production, use APScheduler/Redis worker."""
from __future__ import annotations
from typing import Callable
import threading
import time

class SimpleScheduler:
    def __init__(self):
        self.jobs = []

    def every(self, seconds: int, func: Callable, *args, **kwargs):
        def runner():
            while True:
                try:
                    func(*args, **kwargs)
                except Exception:
                    pass
                time.sleep(seconds)
        t = threading.Thread(target=runner, daemon=True)
        t.start()
        self.jobs.append(t)

