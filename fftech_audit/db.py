
# fftech_audit/db.py
import os
import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey,
    inspect, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fftech_audit.db")

_engine_kwargs = {
    "pool_pre_ping": True,
    "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
    "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
}
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args=_connect_args, **_engine_kwargs)
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
    name = Column(String(255), default="")
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), default="")  # bcrypt hash
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
    grade = Column(String(4))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    user = relationship("User", back_populates="audits")

class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    url = Column(String(2048), nullable=False)
    frequency = Column(String(32), default="weekly")  # 'daily' or 'weekly'
    enabled = Column(Boolean, default=True)
    next_run_at = Column(DateTime, default=datetime.datetime.utcnow)

class MagicLink(Base):
    __tablename__ = "magic_links"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), index=True, nullable=False)
    token = Column(String(512), nullable=False)
    purpose = Column(String(32), default="magic")  # magic or verify
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

Base.metadata.create_all(bind=engine)

def ensure_schedule_columns():
    dialect = engine.dialect.name
    insp = inspect(engine)
    if "schedules" not in insp.get_table_names():
        return
    existing = {col["name"] for col in insp.get_columns("schedules")}
    required = {
        "url": ("VARCHAR(2048)" if dialect == "postgresql" else "TEXT"),
        "frequency": ("VARCHAR(32)" if dialect == "postgresql" else "TEXT"),
        "enabled": ("BOOLEAN" if dialect == "postgresql" else "INTEGER"),
        "next_run_at": ("TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "DATETIME"),
    }
    ddls = []
    for name, typ in required.items():
        if name not in existing:
            if dialect == "postgresql":
                default = " DEFAULT 'weekly'" if name == "frequency" else " DEFAULT TRUE" if name == "enabled" else " DEFAULT NOW()" if name == "next_run_at" else ""
                ddls.append(f"ALTER TABLE schedules ADD COLUMN IF NOT EXISTS {name} {typ}{default};")
            elif dialect == "sqlite":
                default = " DEFAULT 'weekly'" if name == "frequency" else " DEFAULT 1" if name == "enabled" else ""
                ddls.append(f"ALTER TABLE schedules ADD COLUMN {name} {typ}{default};")
            else:
                ddls.append(f"ALTER TABLE schedules ADD COLUMN {name} {typ};")
    if not ddls:
        return
    with engine.begin() as conn:
        for ddl in ddls:
            try:
                conn.execute(text(ddl))
                print(f"[DB] Added column: {ddl}")
            except Exception as e:
                print(f"[DB] DDL failed '{ddl}': {e}")

def ensure_user_columns():
    """Ensure name & password_hash exist for legacy DBs."""
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return
    existing = {col["name"] for col in insp.get_columns("users")}
    ddls = []
    if "name" not in existing:
        ddls.append("ALTER TABLE users ADD COLUMN name TEXT;")
    if "password_hash" not in existing:
        ddls.append("ALTER TABLE users ADD COLUMN password_hash TEXT;")
    with engine.begin() as conn:
        for ddl in ddls:
            try:
                conn.execute(text(ddl)); print(f"[DB] Added column: {ddl}")
            except Exception as e:
                print(f"[DB] DDL failed '{ddl}': {e}")

try:
    ensure_schedule_columns()
    ensure_user_columns()
except Exception as e:
    print(f"[DB] ensure_* failed: {e}")
