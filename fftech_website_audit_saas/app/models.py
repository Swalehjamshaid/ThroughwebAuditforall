from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, DateTime, Boolean, JSON, ForeignKey, Text
from datetime import datetime, timezone
from .database import Base

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    is_subscriber: Mapped[bool] = mapped_column(Boolean, default=False)
    audit_count: Mapped[int] = mapped_column(Integer, default=0) 
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    audits = relationship('Audit', back_populates='user')

class Audit(Base):
    __tablename__ = 'audits'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('users.id'), nullable=True)
    url: Mapped[str] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(JSON) # Stores Metrics A-I
    grade: Mapped[str] = mapped_column(String(10))
    score: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    user = relationship('User', back_populates='audits')

class MagicToken(Base):
    __tablename__ = 'magic_tokens'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    token: Mapped[str] = mapped_column(String(1024), unique=True)
    valid_until: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
