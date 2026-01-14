from sqlalchemy import Column, Integer, String, JSON, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    audit_count = Column(Integer, default=0)

class Audit(Base):
    __tablename__ = "audits"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    url = Column(String)
    score = Column(Integer)
    grade = Column(String)
    result = Column(JSON)  # Stores the Categories A-I
    created_at = Column(DateTime, default=datetime.utcnow)
