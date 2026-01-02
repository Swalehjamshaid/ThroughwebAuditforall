
import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, String, Boolean, Text, Integer, text
)
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()
_engine = None
_SessionLocal = None


def _normalize_database_url(url: str) -> str:
    """
    Normalize DATABASE_URL for SQLAlchemy + psycopg2 and ensure sslmode=require.
    - Convert 'postgres://' to 'postgresql+psycopg2://'
    - Append '&sslmode=require' or '?sslmode=require' with a real ampersand ('&')
    """
    if not url:
        return url

    # SQLAlchemy prefers 'postgresql+psycopg2://'
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    # Append sslmode=require if not already present
    if "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"

    return url


def init_engine():
    """
    Initialize SQLAlchemy engine and session factory from DATABASE_URL.
    Call this once on app startup.
    """
    global _engine, _SessionLocal
    raw_url = os.getenv("DATABASE_URL", "")
    if raw_url:
        url = _normalize_database_url(raw_url)
        _engine = create_engine(
            url,
            pool_pre_ping=True,   # avoids stale connections
            pool_size=5,
            max_overflow=10,
        )
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    else:
        _engine = None
        _SessionLocal = None


def create_schema():
    """
    Create/verify tables once, guarded by a PostgreSQL advisory lock so
    concurrent Gunicorn workers do not race on DDL.

    Safe to call multiple times; only one process will execute DDL and others
    will skip when the lock is held.

    IMPORTANT: Do NOT call this in every worker at import time.
    Gate it behind a one-off init step (env flag) or run with --preload.
    """
    if not _engine:
        return

    # Any constant 64-bit integer works as an advisory lock key:
    LOCK_KEY = 987654321

    # Use transactional connection and lock
    with _engine.begin() as conn:
        got_lock = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar()
        if not got_lock:
            # Another process is doing the DDL; just return.
            return
        try:
            # Bind create_all to the same connection; checkfirst=True by default.
            Base.metadata.create_all(bind=conn)
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})


def get_session():
    return _SessionLocal() if _SessionLocal else None


# ----- Models -----

class User(Base):
    __tablename__ = 'users'
    email = Column(String(255), primary_key=True)
    name = Column(String(255))
    company = Column(String(255))
    role = Column(String(50), default='user')
    password_hash = Column(Text, nullable=False, default='')
    verified = Column(Boolean, default=False)


class Audit(Base):
    __tablename__ = 'audits'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_email = Column(String(255))
    url = Column(Text)
    date = Column(String(20), default=lambda: datetime.utcnow().strftime('%Y-%m-%d'))
    grade = Column(String(5))
    summary = Column(Text)
    overall_score = Column(Integer)  # 0..100 for convenience
