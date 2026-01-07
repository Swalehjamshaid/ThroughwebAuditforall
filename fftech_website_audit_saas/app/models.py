from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import relationship
from .db import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    verified = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    websites = relationship('Website', back_populates='user', cascade='all,delete-orphan')
    audits = relationship('Audit', back_populates='user', cascade='all,delete-orphan')
    subscription = relationship('Subscription', uselist=False, back_populates='user', cascade='all,delete-orphan')

class Website(Base):
    __tablename__ = 'websites'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    url = Column(String(2048), nullable=False)
    last_audit_at = Column(DateTime(timezone=True), nullable=True)
    last_grade = Column(String(8), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship('User', back_populates='websites')
    audits = relationship('Audit', back_populates='website', cascade='all,delete-orphan')

class Audit(Base):
    __tablename__ = 'audits'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    website_id = Column(Integer, ForeignKey('websites.id'), nullable=False, index=True)
    health_score = Column(Integer, nullable=False)
    grade = Column(String(8), nullable=False)
    exec_summary = Column(Text, nullable=True)
    category_scores_json = Column(Text, nullable=True)
    metrics_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship('User', back_populates='audits')
    website = relationship('Website', back_populates='audits')

class Subscription(Base):
    __tablename__ = 'subscriptions'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False, index=True)
    plan = Column(String(32), default='free')
    active = Column(Boolean, default=True)
    audits_used = Column(Integer, default=0)
    daily_time = Column(String(8), default='09:00')
    timezone = Column(String(64), default='UTC')
    email_schedule_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship('User', back_populates='subscription')
