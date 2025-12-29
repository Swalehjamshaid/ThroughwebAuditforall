
import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///fftech.db')
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith('sqlite') else {},
)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    email = Column(String(320), unique=True, index=True)
    plan = Column(String(50), default='free')
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Audit(Base):
    __tablename__ = 'audits'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True, nullable=True)
    url = Column(String(1000))
    metrics_json = Column(Text)
    score = Column(Integer)
    grade = Column(String(5))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Schedule(Base):
    __tablename__ = 'schedules'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    url = Column(String(1000))
    enabled = Column(Boolean, default=True)
    frequency = Column(String(20), default='weekly')  # daily/weekly/monthly
    scheduled_hour = Column(Integer, default=9)
    scheduled_minute = Column(Integer, default=0)
    timezone = Column(String(64), default='UTC')
    next_run_at = Column(DateTime(timezone=True), nullable=True)
