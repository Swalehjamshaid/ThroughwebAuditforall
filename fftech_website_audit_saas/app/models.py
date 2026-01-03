
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .db import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    verified = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    status = Column(String(32), default='active')
    created_at = Column(DateTime, default=datetime.utcnow)
    audits = relationship('Audit', back_populates='user')

class Website(Base):
    __tablename__ = 'websites'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    url = Column(String(2048), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_audit_at = Column(DateTime, nullable=True)
    last_grade = Column(String(8), nullable=True)
    audits = relationship('Audit', back_populates='website')

class Audit(Base):
    __tablename__ = 'audits'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    website_id = Column(Integer, ForeignKey('websites.id'))
    created_at = Column(DateTime, default=datetime.utcnow)
    health_score = Column(Integer, default=0)
    grade = Column(String(8), default='D')
    exec_summary = Column(Text, default='')
    category_scores_json = Column(Text, default='[]')
    metrics_json = Column(Text, default='[]')
    user = relationship('User', back_populates='audits')
    website = relationship('Website', back_populates='audits')

class Subscription(Base):
    __tablename__ = 'subscriptions'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    plan = Column(String(64), default='free')
    active = Column(Boolean, default=True)
    audits_used = Column(Integer, default=0)
