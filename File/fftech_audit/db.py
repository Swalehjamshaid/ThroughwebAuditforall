
# fftech_audit/db.py
import os
import datetime as dt
from typing import Optional
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, Session, relationship

# --- Engine & session setup ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "audit.sqlite3")

DATABASE_URL = os.getenv("DATABASE_URL")  # Railway provides Postgres URL
if DATABASE_URL:
    # SQLAlchemy expects 'postgresql://'
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")
    engine = create_engine(DATABASE_URL)
else:
    engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


# --- Models ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    plan = Column(String(50), default="free")  # 'free' or 'subscriber'
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    url = Column(String(1024), nullable=False)
    frequency = Column(String(32), default="weekly")  # daily/weekly/monthly
    time_of_day = Column(String(16), default="09:00")  # HH:MM in UTC
    timezone = Column(String(64), default="UTC")
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    user = relationship("User")


class AuditHistory(Base):
    __tablename__ = "audit_history"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # nullable for open-access audits
    url = Column(String(1024), nullable=False)
    health_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    user = relationship("User")


# --- Init ---
def init_db():
    """Create tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


# --- User helpers ---
def upsert_user(db: Session, email: str) -> User:
    """Find a user by email, creating it if missing."""
    u = db.query(User).filter(User.email == email).first()
    if not u:
        u = User(email=email)
        db.add(u)
        db.commit()
        db.refresh(u)
    return u


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


# --- Schedule helpers ---
def save_schedule(
    db: Session,
    user_id: int,
    url: str,
    frequency: str,
    time_of_day: str,
    timezone: str,
) -> Schedule:
    s = Schedule(
        user_id=user_id,
        url=url,
        frequency=frequency,
        time_of_day=time_of_day,
        timezone=timezone,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# --- Audit history helpers ---
def create_audit_history(
    db: Session,
    url: str,
    health_score: float,
    user_id: Optional[int] = None,
) -> AuditHistory:
    a = AuditHistory(url=url, health_score=health_score, user_id=user_id)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def count_user_audits(db: Session, user_id: int) -> int:
    return db.query(AuditHistory).filter(AuditHistory.user_id == user_id).count()


# --- Scheduling time helper (UTC, simple) ---
def compute_next_run_utc(frequency: str, time_of_day: str) -> dt.datetime:
    """
    Compute next run time in UTC based on frequency and HH:MM.
    This is a simple calculator (no timezone conversion). For real TZs, use zoneinfo/pytz.
    """
    now = dt.datetime.utcnow()
    try:
        hour, minute = (time_of_day or "09:00").split(":")
        hour = int(hour)
        minute = int(minute)
    except Exception:
        hour, minute = 9, 0

    if frequency == "daily":
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += dt.timedelta(days=1)
        return target

    if frequency == "weekly":
        # Schedule next occurrence of the same weekday/time; if already passed today, go 7 days ahead
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += dt.timedelta(days=7)
        return target

    if frequency == "monthly":
        # Next month, same day where possible (cap at 28 to avoid invalid dates)
        year = now.year
        month = now.month + 1
        if month > 12:
            month = 1
            year += 1
        day = min(now.day, 28)
        return dt.datetime(year, month, day, hour, minute)

    # Default: weekly one week later
    target = now + dt.timedelta(days=7)
    return target.replace(hour=hour, minute=minute, second=0, microsecond=0)
``
