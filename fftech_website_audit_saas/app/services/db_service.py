
"""Database service using SQLAlchemy for Railway PostgreSQL.
Env: DATABASE_URL=postgresql+psycopg2://user:pass@host:port/db
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
import os

from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv('DATABASE_URL')

Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False,
                            bind=create_engine(DATABASE_URL) if DATABASE_URL else None)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    audits_left = Column(Integer, default=10)  # free tier limit

class Audit(Base):
    __tablename__ = 'audits'
    id = Column(Integer, primary_key=True)
    user_email = Column(String, index=True, nullable=True)
    url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    metrics = Column(JSON)
    overall_score = Column(Integer)
    grade = Column(String)


def init_db():
    if DATABASE_URL:
        engine = create_engine(DATABASE_URL)
        Base.metadata.create_all(engine)

