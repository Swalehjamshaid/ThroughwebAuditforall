
from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, ForeignKey, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from .db import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    is_verified = Column(Boolean, default=False)
    subscription = Column(String, default='free')
    audits = relationship('Audit', back_populates='user')

class Audit(Base):
    __tablename__ = 'audits'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    url = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default='completed')
    summary = Column(JSON, default={})
    metrics = Column(JSON, default={})
    category_scores = Column(JSON, default={})
    overall_score = Column(Float, default=0.0)
    grade = Column(String, default='D')
    report_pdf_path = Column(String, nullable=True)

    user = relationship('User', back_populates='audits')

class Schedule(Base):
    __tablename__ = 'schedules'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    url = Column(String, nullable=False)
    cron = Column(String, nullable=False)
    active = Column(Boolean, default=True)
