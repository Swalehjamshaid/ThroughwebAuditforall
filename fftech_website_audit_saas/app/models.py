from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, DateTime, Boolean, JSON, ForeignKey, Text
from datetime import datetime, timezone
from app.database import Base # Use absolute import

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    is_subscriber: Mapped[bool] = mapped_column(Boolean, default=False)
    audit_count: Mapped[int] = mapped_column(Integer, default=0)
    audits = relationship('Audit', back_populates='user')
    schedules = relationship('AuditSchedule', back_populates='user')

class Audit(Base):
    __tablename__ = 'audits'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('users.id'), nullable=True)
    url: Mapped[str] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(JSON) # Category A-I results
    grade: Mapped[str] = mapped_column(String(10))
    score: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    user = relationship('User', back_populates='audits')

class AuditSchedule(Base):
    __tablename__ = 'audit_schedules'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'))
    target_url: Mapped[str] = mapped_column(String(500))
    hour: Mapped[int] = mapped_column(Integer)
    day_of_week: Mapped[str] = mapped_column(String(20))
    user = relationship('User', back_populates='schedules')
