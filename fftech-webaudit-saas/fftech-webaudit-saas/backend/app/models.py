from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, Text
from datetime import datetime

Base = declarative_base()

class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    role = Column(String(50), default="user")  # admin|manager|user
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Website(Base):
    __tablename__ = "websites"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"))
    url = Column(String(1024), nullable=False)
    label = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

class Audit(Base):
    __tablename__ = "audits"
    id = Column(Integer, primary_key=True)
    website_id = Column(Integer, ForeignKey("websites.id", ondelete="CASCADE"))
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    grade = Column(String(3))  # A+, A, B, C, D
    score_overall = Column(Float)
    details_json = Column(Text)  # store per-metric scores/issues

class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    website_id = Column(Integer, ForeignKey("websites.id", ondelete="CASCADE"))
    cron = Column(String(64))  # e.g. "0 9 * * *" daily at 9
    timezone = Column(String(64), default="UTC")
    active = Column(Boolean, default=True)
