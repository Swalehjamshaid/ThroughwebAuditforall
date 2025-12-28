
# db.py
"""
Database integration (SQLAlchemy)
- Engine & SessionLocal
- Models: User, Audit, Schedule, MagicLink, EmailCode
"""

import os, datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fftech_audit.db")

Base = declarative_base()
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

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
    url = Column(String(2048), nullable=False)
    frequency = Column(String(32), default="weekly")  # daily|weekly|monthly
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
