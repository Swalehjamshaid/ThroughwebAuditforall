from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON, Float
from datetime import datetime

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    email_verified = Column(Boolean, default=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), default="user")  # user, admin
    created_at = Column(DateTime, default=datetime.utcnow)
    audits = relationship("AuditJob", back_populates="owner")

class AuditJob(Base):
    __tablename__ = "audit_jobs"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    target_url = Column(String(2048), nullable=False)
    schedule = Column(String(100), nullable=True)  # cron or daily time
    timezone = Column(String(100), default="UTC")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", back_populates="audits")
    runs = relationship("AuditRun", back_populates="job")

class AuditRun(Base):
    __tablename__ = "audit_runs"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("audit_jobs.id"))
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    status = Column(String(50), default="pending")  # pending, success, failed
    lighthouse_report = Column(JSON)
    metrics_summary = Column(JSON)  # aggregated metrics
    grade = Column(String(3))  # A+, A, B, C, D
    score = Column(Float)
    job = relationship("AuditJob", back_populates="runs")

class CertifiedReport(Base):
    __tablename__ = "certified_reports"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("audit_runs.id"), nullable=False)
    pdf_path = Column(String(512), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
