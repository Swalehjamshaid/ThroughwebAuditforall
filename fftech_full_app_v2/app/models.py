
from sqlalchemy import Column, Integer, String, JSON, Float, Text, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    subscription = Column(String(50), default="free")
    audits = relationship("Audit", back_populates="user")

class Audit(Base):
    __tablename__ = "audits"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    url = Column(String(2048), nullable=False)
    overall_score = Column(Float, nullable=False)
    grade = Column(String(5), nullable=False)
    summary = Column(JSON)
    category_scores = Column(JSON)
    metrics = Column(JSON)
    report_pdf_path = Column(Text, nullable=True)

    user = relationship("User", back_populates="audits")
