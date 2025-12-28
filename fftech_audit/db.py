
# fftech_audit/db.py
"""
Database integration (SQLAlchemy)
- Engine & SessionLocal tuned with pool_pre_ping and bounded pool size to avoid overflow
- Models: User, Audit, Schedule, MagicLink, EmailCode
- Auto-remediation: ensure 'schedules' table has required columns (url, frequency, enabled, next_run_at)
"""

import os
import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, inspect, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fftech_audit.db")

# Tune the engine to reduce pool exhaustion and keep connections healthy
_engine_kwargs = {
    "pool_pre_ping": True,
}
# Pool sizing (ignored by SQLite, respected by Postgres/MySQL)
_pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
_max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
_engine_kwargs.update({"pool_size": _pool_size, "max_overflow": _max_overflow})

# SQLite-specific connect args
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

Base = declarative_base()
engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    **_engine_kwargs,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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
    url = Column(String(2048), nullable=False)         # REQUIRED
    frequency = Column(String(32), default="weekly")   # REQUIRED: daily|weekly|monthly
    enabled = Column(Boolean, default=True)            # REQUIRED
    next_run_at = Column(DateTime, default=datetime.datetime.utcnow)  # REQUIRED

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

# Create tables if missing (does NOT add columns to existing tables)
Base.metadata.create_all(bind=engine)

def ensure_schedule_columns():
    """
    Auto-remediate the 'schedules' table to ensure required columns exist.
    Works for PostgreSQL and SQLite. Safe to run on startup.
    """
    dialect = engine.dialect.name  # 'postgresql', 'sqlite', 'mysql', etc.
    insp = inspect(engine)
    tables = insp.get_table_names()
    if "schedules" not in tables:
        # Table missing; create via metadata (already done above)
        return

    existing_cols = {col["name"] for col in insp.get_columns("schedules")}
    required = {
        "url": ("VARCHAR(2048)" if dialect == "postgresql" else "TEXT"),
        "frequency": ("VARCHAR(32)" if dialect == "postgresql" else "TEXT"),
        "enabled": ("BOOLEAN" if dialect == "postgresql" else "INTEGER"),
        "next_run_at": ("TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "DATETIME"),
    }

    # Build DDL per missing column
    ddls = []
    for col_name, col_type in required.items():
        if col_name not in existing_cols:
            if dialect == "postgresql":
                # Postgres supports IF NOT EXISTS for ADD COLUMN
                default_clause = ""
                if col_name == "frequency":
                    default_clause = " DEFAULT 'weekly'"
                elif col_name == "enabled":
                    default_clause = " DEFAULT TRUE"
                elif col_name == "next_run_at":
                    default_clause = " DEFAULT NOW()"
                ddl = f"ALTER TABLE schedules ADD COLUMN IF NOT EXISTS {col_name} {col_type}{default_clause};"
                ddls.append(ddl)
            elif dialect == "sqlite":
                # SQLite (older versions) may not support IF NOT EXISTS; we guard by checking columns above.
                # Use reasonable defaults.
                default_clause = ""
                if col_name == "frequency":
                    default_clause = " DEFAULT 'weekly'"
                elif col_name == "enabled":
                    default_clause = " DEFAULT 1"
                ddl = f"ALTER TABLE schedules ADD COLUMN {col_name} {col_type}{default_clause};"
                ddls.append(ddl)
            else:
                # Fallback generic SQL
                ddl = f"ALTER TABLE schedules ADD COLUMN {col_name} {col_type};"
                ddls.append(ddl)

    if not ddls:
        return

    # Execute DDLs
    with engine.begin() as conn:
        for ddl in ddls:
            try:
                conn.execute(text(ddl))
            except Exception as e:
                # If column already exists or dialect limitation, ignore/log and continue
                print(f"[DB] ensure_schedule_columns: DDL failed '{ddl}': {e}")

# Run auto-remediation at import/startup
try:
    ensure_schedule_columns()
except Exception as e:
    print(f"[DB] ensure_schedule_columns failed: {e}")
