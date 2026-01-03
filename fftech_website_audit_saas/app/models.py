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
    is_admin = Column(Boolean, default=False)
    timezone = Column(String, default="UTC")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    plan = Column(String, default="free")
    status = Column(String, default="active")
    quota_used = Column(Integer, default=0)
    quota_limit = Column(Integer, default=10)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    renewed_at = Column(DateTime)

class Website(Base):
    __tablename__ = "websites"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    url = Column(String)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Audit(Base):
    __tablename__ = "audits"
    id = Column(Integer, primary_key=True)
    website_id = Column(Integer, ForeignKey("websites.id"))
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    grade = Column(String)
    overall_score = Column(Integer)
    summary_200_words = Column(Text)
    json_metrics = Column(JSON)

class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"
    token = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    expires_at = Column(DateTime)
    used = Column(Boolean, default=False)
