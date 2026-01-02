
import os
from sqlalchemy import create_engine, Column, String, Boolean, Text, Integer
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

Base = declarative_base()
_engine = None
_SessionLocal = None

def init_engine():
    global _engine, _SessionLocal
    url = os.getenv('DATABASE_URL')
    if url:
        if 'sslmode' not in url:
            sep = '&' if '?' in url else '?'
            url = f"{url}{sep}sslmode=require"
        _engine = create_engine(url, pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    else:
        _engine = None
        _SessionLocal = None

def create_schema():
    if _engine:
        Base.metadata.create_all(_engine)

def get_session():
    return _SessionLocal() if _SessionLocal else None

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
