
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .db import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True)
    is_paid = Column(Boolean, default=False)
    audits = relationship('Audit', back_populates='user')
    created_at = Column(DateTime, default=datetime.utcnow)

class Audit(Base):
    __tablename__ = 'audits'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True) # null for open access
    url = Column(String, nullable=False)
    status = Column(String, default='completed')
    score = Column(Integer, default=0)
    grade = Column(String, default='D')
    coverage = Column(Integer, default=0)
    metrics = Column(JSON)  # dict of metric_id -> {value, score, notes}
    summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship('User', back_populates='audits')

class Subscription(Base):
    __tablename__ = 'subscriptions'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    plan = Column(String, default='free') # free | pro | enterprise
    active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
