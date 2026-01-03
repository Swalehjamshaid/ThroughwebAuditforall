import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    email_verified = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False) # Admin login attribute
    timezone = Column(String, default="UTC")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    plan = Column(String, default="free") # "free" or "premium"
    status = Column(String, default="active")
    quota_used = Column(Integer, default=0)
    quota_limit = Column(Integer, default=10) # 10 Audits limit
    started_at = Column(DateTime, default=datetime.datetime.utcnow)

class Website(Base):
    __tablename__ = "websites"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    url = Column(String)
    active = Column(Boolean, default=True)

class Audit(Base):
    __tablename__ = "audits"
    id = Column(Integer, primary_key=True)
    website_id = Column(Integer, ForeignKey("websites.id"))
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    grade = Column(String) # A+, A, B, C, D
    overall_score = Column(Integer) # 0-100
    summary_200_words = Column(Text) # AI/Business Summary
    json_metrics = Column(JSON) # Stores 140+ metrics
