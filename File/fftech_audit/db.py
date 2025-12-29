
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.ext.hybrid import hybrid_property
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=True)
    is_verified = Column(Boolean, default=False, nullable=False)
    plan = Column(String, default="free", nullable=False)
    audits_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    audits = relationship("Audit", back_populates="user", cascade="all, delete-orphan")

    @hybrid_property
    def verified(self):
        return bool(self.is_verified)

    @verified.setter
    def verified(self, v):
        self.is_verified = bool(v)

    @verified.expression
    def verified(cls):
        return cls.is_verified

class Audit(Base):
    __tablename__ = "audits"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    url = Column(String, nullable=False)
    metrics_json = Column(Text, nullable=False)
    score = Column(Integer, nullable=False)
    grade = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="audits")

class MagicLink(Base):
    __tablename__ = 'magic_links'
    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False, index=True)
    token = Column(String, nullable=False, unique=True)
    purpose = Column(String, default='verify')
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    consumed = Column(Boolean, default=False)

class EmailCode(Base):
    __tablename__ = 'email_codes'
    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False, index=True)
    code = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# Database connection
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///local.db')
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
