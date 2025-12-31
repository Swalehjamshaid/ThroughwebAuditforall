
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, UniqueConstraint, Boolean
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.types import JSON

try:
    from sqlalchemy.dialects.postgresql import JSONB as JSONType
except Exception:
    JSONType = JSON

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    role = Column(String(20), nullable=False, default="viewer")
    audits = relationship("Audit", back_populates="user", cascade="all, delete-orphan")

class Audit(Base):
    __tablename__ = "audits"
    id = Column(String(36), primary_key=True)
    site_url = Column(Text, nullable=False)
    overall_score = Column(Integer, nullable=False)
    grade = Column(String(3), nullable=False)
    result = Column(JSONType, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    user = relationship("User", back_populates="audits")
    metrics = relationship("AuditMetric", back_populates="audit", cascade="all, delete-orphan")

class AuditMetric(Base):
    __tablename__ = "audit_metrics"
    id = Column(Integer, primary_key=True)
    audit_id = Column(String(36), ForeignKey("audits.id"), nullable=False, index=True)
    category = Column(String(50), nullable=False)
    code = Column(Integer, nullable=False, default=0)
    name = Column(String(100), nullable=False)
    value = Column(Integer, nullable=True)
    severity = Column(String(20), nullable=True)
    impact = Column(Integer, nullable=True)
    priority = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    audit = relationship("Audit", back_populates="metrics")
    __table_args__ = (UniqueConstraint("audit_id", "category", "code", name="uq_audit_category_code"),)

class MagicLinkToken(Base):
    __tablename__ = "magic_link_tokens"
    token = Column(String(64), primary_key=True)
    email = Column(String(255), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    redeemed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    user = relationship("User")
