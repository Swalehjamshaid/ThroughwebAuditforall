
# fftech_audit/db.py
"""
Database integration (SQLAlchemy) + Auto-remediation for schedules table

Fixes:
- (psycopg2.errors.UndefinedColumn) column schedules.url does not exist
- Connection pool overflow by enabling pool_pre_ping and bounding pool size

What this file does:
- Defines models: User, Audit, Schedule, MagicLink, EmailCode
- Creates tables if missing (create_all)
- Adds missing columns to 'schedules' table at startup: url, frequency, enabled, next_run_at
- Tunes SQLAlchemy engine pool for Postgres deployments

Usage:
- Drop-in replacement for your current fftech_audit/db.py
- No external migrations required (one-time DDL executed at startup)
"""

import os
import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey,
    inspect, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# ---------------- Config ----------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fftech_audit.db")

# Engine tuning to reduce pool errors (ignored by SQLite, used by Postgres/MySQL)
_engine_kwargs = {
    "pool_pre_ping": True,                               # refresh dead connections
    "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),    # base pool size
    "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),  # overflow connections
}
# SQLite needs check_same_thread=False; Postgres/MySQL don't
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# ---------------- SQLAlchemy Setup ----------------
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args=_connect_args, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

def get_db():
    """FastAPI dependency for a scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------- Models ----------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    verified = Column(Boolean, default=False)
    plan = Column(String(32), default="free")  # free|pro|enterprise
    audits_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    audits = relationship("Audit", back_populates="user")

class Audit(Base):
    __tablename__ = "audits"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    url = Column(String(2048), nullable=False)
    metrics_json = Column(Text)
    score = Column(Integer)
    grade = Column(String(4))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    user = relationship("User", back_populates="audits")

class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # These columns MUST exist in the DB to avoid your errors:
    url = Column(String(2048), nullable=False)
    frequency = Column(String(32), default="weekly")     # daily|weekly|monthly
    enabled = Column(Boolean, default=True)
    next_run_at = Column(DateTime, default=datetime.datetime.utcnow)

class MagicLink(Base):
    __tablename__ = "magic_links"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), index=True, nullable=False)
    token = Column(String(512), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class EmailCode(Base):
    __tablename__ = "email_codes"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), index=True, nullable=False)
    code = Column(String(12), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# Create tables if missing (NOTE: create_all does NOT add columns to existing tables)
Base.metadata.create_all(bind=engine)

# ---------------- Auto-remediation for schedules table ----------------
def ensure_schedule_columns():
    """
    Add missing columns to 'schedules' (url, frequency, enabled, next_run_at) at startup.
    Works for PostgreSQL and SQLite. Safe to run repeatedly.
    """
    dialect = engine.dialect.name  # 'postgresql', 'sqlite', 'mysql', ...
    insp = inspect(engine)
    table_names = insp.get_table_names()

    if "schedules" not in table_names:
        # Table absent: already created above via create_all, but return here just in case.
        return

    existing_cols = {col["name"] for col in insp.get_columns("schedules")}

    # Column types per dialect
    required = {
        "url": ("VARCHAR(2048)" if dialect == "postgresql" else "TEXT"),
        "frequency": ("VARCHAR(32)" if dialect == "postgresql" else "TEXT"),
        "enabled": ("BOOLEAN" if dialect == "postgresql" else "INTEGER"),
        "next_run_at": ("TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "DATETIME"),
    }

    ddls = []
    for col_name, col_type in required.items():
        if col_name not in existing_cols:
            if dialect == "postgresql":
                # Postgres: IF NOT EXISTS is supported; include sensible DEFAULTs
                default_clause = ""
                if col_name == "frequency":
                    default_clause = " DEFAULT 'weekly'"
                elif col_name == "enabled":
                    default_clause = " DEFAULT TRUE"
                elif col_name == "next_run_at":
                    default_clause = " DEFAULT NOW()"
                ddl = f"ALTER TABLE schedules ADD COLUMN IF NOT EXISTS {col_name} {col_type}{default_clause};"
            elif dialect == "sqlite":
                # SQLite: older versions may not support IF NOT EXISTS on ADD COLUMN;
                # we guarded above by checking existing_cols.
                default_clause = ""
                if col_name == "frequency":
                    default_clause = " DEFAULT 'weekly'"
                elif col_name == "enabled":
                    default_clause = " DEFAULT 1"
                ddl = f"ALTER TABLE schedules ADD COLUMN {col_name} {col_type}{default_clause};"
            else:
                # Generic fallback
                ddl = f"ALTER TABLE schedules ADD COLUMN {col_name} {col_type};"
            ddls.append(ddl)

    if not ddls:
        return  # nothing to do

    # Execute DDL safely in a transaction
    with engine.begin() as conn:
        for ddl in ddls:
            try:
                conn.execute(text(ddl))
                print(f"[DB] Added missing column via DDL: {ddl}")
            except Exception as e:
                # Don't crash the app; log and continue
                print(f"[DB] ensure_schedule_columns: DDL failed '{ddl}': {e}")

# Run auto-remediation at import/startup
try:
    ensure_schedule_columns()
except Exception as e:
    print(f"[DB] ensure_schedule_columns failed: {e}")
