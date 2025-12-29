
# fftech_audit/db.py
import os
import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, inspect, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# ---- Engine & Session ----
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fftech_audit.db")
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)

Base = declarative_base()

def get_db():
    """FastAPI dependency: yields a DB session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---- Models ----
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), default="")
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), default="")
    verified = Column(Boolean, default=False)
    plan = Column(String(32), default="free")
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
    grade = Column(String(8))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    user = relationship("User", back_populates="audits")

class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    url = Column(String(2048), nullable=False)
    frequency = Column(String(32), default="weekly")  # e.g., daily | weekly
    enabled = Column(Boolean, default=True)
    next_run_at = Column(DateTime, default=datetime.datetime.utcnow)

class MagicLink(Base):
    __tablename__ = "magic_links"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), index=True, nullable=False)
    token = Column(String(512), nullable=False)
    purpose = Column(String(32), default="verify")  # verify | magic
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class EmailCode(Base):
    """
    Optional one-time code flow (Phase 2).
    If EMAIL_VERIFICATION_MODE=code, we store numeric codes here.
    """
    __tablename__ = "email_codes"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), index=True, nullable=False)
    code = Column(String(16), nullable=False)  # e.g., 6-digit
    purpose = Column(String(32), default="verify")  # verify | login
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# ---- Create tables ----
Base.metadata.create_all(bind=engine)

# ---- DDL helpers (safe add columns if missing) ----
def ensure_schedule_columns():
    insp = inspect(engine)
    if "schedules" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("schedules")}
    with engine.begin() as conn:
        add_stmts = [
            ("url", "ALTER TABLE schedules ADD COLUMN url TEXT"),
            ("frequency", "ALTER TABLE schedules ADD COLUMN frequency TEXT DEFAULT 'weekly'"),
            ("enabled", "ALTER TABLE schedules ADD COLUMN enabled INTEGER DEFAULT 1"),
            ("next_run_at", "ALTER TABLE schedules ADD COLUMN next_run_at DATETIME"),
        ]
        for name, ddl in add_stmts:
            if name not in existing:
                try:
                    conn.execute(text(ddl))
                except Exception as e:
                    print("[DB] DDL failed:", ddl, e)

def ensure_user_columns():
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("users")}
    with engine.begin() as conn:
        add_stmts = [
            ("name", "ALTER TABLE users ADD COLUMN name TEXT"),
            ("password_hash", "ALTER TABLE users ADD COLUMN password_hash TEXT"),
            ("plan", "ALTER TABLE users ADD COLUMN plan TEXT"),
            ("audits_count", "ALTER TABLE users ADD COLUMN audits_count INTEGER DEFAULT 0"),
        ]
        for name, ddl in add_stmts:
            if name not in existing:
                try:
                    conn.execute(text(ddl))
                except Exception as e:
                    print("[DB] DDL failed:", ddl, e)
