
import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, String, Boolean, Text, Integer, DateTime, ForeignKey, text
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

Base = declarative_base()
_engine = None
_SessionLocal = None

# ---------- URL normalization ----------
def _normalize_database_url(url: str) -> str:
    if not url:
        return url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url

# ---------- Engine & Session ----------
def init_engine():
    global _engine, _SessionLocal
    raw = os.getenv("DATABASE_URL", "")
    if raw:
        url = _normalize_database_url(raw)
        _engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    else:
        _engine = None
        _SessionLocal = None


def create_schema():
    """Create tables once, guarded by PostgreSQL advisory lock to avoid races."""
    if not _engine:
        return
    LOCK_KEY = 987654321
    with _engine.begin() as conn:
        got_lock = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar()
        if not got_lock:
            return
        try:
            Base.metadata.create_all(bind=conn)
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})


def get_db():
    return _SessionLocal() if _SessionLocal else None

# ---------- Models ----------
class User(Base):
    __tablename__ = "users"
    email = Column(String(255), primary_key=True)
    name = Column(String(255))
    company = Column(String(255))
    role = Column(String(50), default="user")
    password_hash = Column(Text, nullable=False, default="")
    verified = Column(Boolean, default=False)
    audits_remaining = Column(Integer, default=10)  # 10 free audits
    subscribed = Column(Boolean, default=False)     # $5/month when true
    created_at = Column(DateTime, default=datetime.utcnow)

    sites = relationship("Site", back_populates="owner")
    schedules = relationship("Schedule", back_populates="user")

class VerificationToken(Base):
    __tablename__ = "verification_tokens"
    token = Column(String(255), primary_key=True)
    email = Column(String(255), ForeignKey("users.email"))
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class Site(Base):
    __tablename__ = "sites"
    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_email = Column(String(255), ForeignKey("users.email"))
    url = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", back_populates="sites")

class Audit(Base):
    __tablename__ = "audits"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_email = Column(String(255))
    site_id = Column(Integer, ForeignKey("sites.id"))
    url = Column(Text)
    date = Column(String(20), default=lambda: datetime.utcnow().strftime("%Y-%m-%d"))
    grade = Column(String(5))
    summary = Column(Text)
    overall_score = Column(Integer)      # 0..100
    metrics_json = Column(Text)          # Detailed JSON blob (140+ metrics)

class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_email = Column(String(255), ForeignKey("users.email"))
    site_id = Column(Integer, ForeignKey("sites.id"))
    cron_time = Column(String(10))       # "HH:MM"
    type = Column(String(20), default="daily")  # "daily" or "accumulated"
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="schedules")
