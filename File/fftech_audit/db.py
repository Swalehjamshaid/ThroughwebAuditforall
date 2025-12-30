
# fftech_audit/db.py
import os
import datetime as dt
from typing import Optional
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float
from sqlalchemy.orm import sessionmaker, declarative_base, Session

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "audit.sqlite3")

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    url = Column(String(1024), nullable=False)
    frequency = Column(String(32), default="weekly")
    time_of_day = Column(String(16), default="09:00")
    timezone = Column(String(64), default="UTC")
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class AuditHistory(Base):
    __tablename__ = "audit_history"
    id = Column(Integer, primary_key=True)
    url = Column(String(1024), nullable=False)
    health_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=dt.datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def upsert_user(db: Session, email: str) -> User:
    u = db.query(User).filter(User.email == email).first()
    if not u:
        u = User(email=email)
        db.add(u)
        db.commit()
        db.refresh(u)
    return u


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


def save_schedule(db: Session, url: str, frequency: str, time_of_day: str, timezone: str) -> Schedule:
    s = Schedule(url=url, frequency=frequency, time_of_day=time_of_day, timezone=timezone)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def create_audit_history(db: Session, url: str, health_score: float) -> AuditHistory:
    a = AuditHistory(url=url, health_score=health_score)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def compute_next_run_utc(frequency: str, time_of_day: str) -> dt.datetime:
    """
    Without external tz libs, compute next run in UTC assuming given time_of_day is UTC.
    For real tz conversion, use 'pytz'/'zoneinfo'.
    """
    now = dt.datetime.utcnow()
    hour, minute = (time_of_day or "09:00").split(":")
    target_time_today = now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
    if frequency == "daily":
        next_run = target_time_today if target_time_today > now else (target_time_today + dt.timedelta(days=1))
    elif frequency == "weekly":
        # next same weekday at time
        next_run = target_time_today
        if next_run <= now:
            next_run = next_run + dt.timedelta(days=1)
        # push forward until we hit next week boundary from "now.weekday()"
        # simplest approach: add 7 days when we cross
        next_run = now + dt.timedelta(days=(7 - now.weekday()))  # next Monday
        next_run = next_run.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
    elif frequency == "monthly":
        # next month, same day if possible
        year = now.year
        month = now.month + 1
        if month > 12:
            month = 1
            year += 1
        day = min(now.day, 28)  # avoid invalid dates in short months
        next_run = dt.datetime(year, month, day, int(hour), int(minute))
    else:
        # default: weekly
        next_run = now + dt.timedelta(days=7)
        next_run = next_run.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
    return next_run
``
