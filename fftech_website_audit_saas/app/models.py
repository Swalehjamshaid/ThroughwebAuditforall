
from __future__ import annotations
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import Mapped
from datetime import datetime
from .db import Base

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    email: Mapped[str] = Column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = Column(String(255), nullable=True)
    hashed_password: Mapped[str] = Column(String(255), nullable=False)
    is_admin: Mapped[bool] = Column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, nullable=False)
