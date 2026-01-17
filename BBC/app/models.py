from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    is_subscribed = Column(Boolean, default=False)
    audits = relationship('AuditJob', back_populates='user')

class AuditJob(Base):
    __tablename__ = 'audit_jobs'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    target_url = Column(String(2048), nullable=False)
    status = Column(String(50), default='completed')
    created_at = Column(DateTime, default=datetime.utcnow)
    result = relationship('AuditResult', back_populates='job', uselist=False)
    user = relationship('User', back_populates='audits')

class AuditResult(Base):
    __tablename__ = 'audit_results'
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey('audit_jobs.id'))
    metrics = Column(JSON)
    scores = Column(JSON)
    pdf_path = Column(String(1024))
    created_at = Column(DateTime, default=datetime.utcnow)
    job = relationship('AuditJob', back_populates='result')

class MonitoredTarget(Base):
    __tablename__ = 'monitored_targets'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    url = Column(String(2048), nullable=False)
    cadence = Column(String(32), default='weekly')
    last_run = Column(DateTime, nullable=True)
    active = Column(Boolean, default=True)
    user = relationship('User')
