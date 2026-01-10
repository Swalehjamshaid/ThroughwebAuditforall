
from __future__ import annotations
from sqlalchemy.orm import declarative_base, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, Text
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    token: Mapped[str] = mapped_column(String(255), nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    plan: Mapped[str] = mapped_column(String(50), default='free')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    audits: Mapped[list['AuditRun']] = relationship('AuditRun', back_populates='user')

class AuditRun(Base):
    __tablename__ = 'audit_runs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('users.id'), nullable=True)
    url: Mapped[str] = mapped_column(String(2048))
    score: Mapped[int] = mapped_column(Integer, default=0)
    grade: Mapped[str] = mapped_column(String(4), default='D')
    metrics_json: Mapped[str] = mapped_column(Text)
    pdf_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    graphs_json: Mapped[str] = mapped_column(Text, default='[]')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped['User'] = relationship('User', back_populates='audits')

