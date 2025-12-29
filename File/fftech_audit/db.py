
# fftech_audit/db.py
import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from datetime import datetime

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./fftech.db')
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=True)
    plan = Column(String(50), default='free')
    is_verified = Column(Boolean, default=False)
    audits_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    audits = relationship('Audit', back_populates='user')

class Audit(Base):
    __tablename__ = 'audits'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    url = Column(String(512), nullable=False)
    metrics_json = Column(Text, nullable=False)
    score = Column(Integer, default=0)
    grade = Column(String(5), default='F')
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship('User', back_populates='audits')

class Schedule(Base):
    __tablename__ = 'schedules'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    url = Column(String(512), nullable=False)
    frequency = Column(String(20), default='weekly')  # 'daily' or 'weekly'
    enabled = Column(Boolean, default=False)
    next_run_at = Column(DateTime, default=datetime.utcnow)

    # New: desired local time and timezone
    scheduled_hour = Column(Integer, default=9)      # 0..23
    scheduled_minute = Column(Integer, default=0)    # 0..59
    timezone = Column(String(64), default='Asia/Karachi')

    user = relationship('User')
