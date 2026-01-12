# app/models.py
from sqlalchemy import Column, Integer, String, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from .db import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    verified = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    websites = relationship('Website', back_populates='user')

class Website(Base):
    __tablename__ = 'websites'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    url = Column(String(1024), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_audit_at = Column(DateTime, nullable=True)
    last_grade = Column(String(4), nullable=True)
    user = relationship('User', back_populates='websites')
    audits = relationship('Audit', back_populates='website')

class Audit(Base):
    __tablename__ = 'audits'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    website_id = Column(Integer, ForeignKey('websites.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    health_score = Column(Integer, default=0)
    grade = Column(String(4), default='C')
    exec_summary = Column(Text, default='')
    category_scores_json = Column(Text, default='')
    metrics_json = Column(Text, default='')
    website = relationship('Website', back_populates='audits')

class Subscription(Base):
    __tablename__ = 'subscriptions'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    plan = Column(String(32), default='free')
    active = Column(Boolean, default=True)
    audits_used = Column(Integer, default=0)
    daily_time = Column(String(8), default='09:00')
    timezone = Column(String(64), default='UTC')
    email_schedule_enabled = Column(Boolean, default=False)
