from __future__ import annotations
from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from datetime import datetime
import os, hashlib, hmac

from .db import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=True)
    is_admin = Column(Boolean, default=False)
    verified = Column(Boolean, default=False) # For Magic Link flow
    audits_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    audits = relationship('Audit', back_populates='user', cascade='all,delete')

class Audit(Base):
    __tablename__ = 'audits'
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(2048), nullable=False)
    
    # Standard Compliance Pillars (1-200 Metrics)
    health_score = Column(Float, default=0.0) # Overall 0-100
    grade = Column(String(5))                 # A+ to D
    
    # Metrics Storage
    category_scores_json = Column(Text, nullable=True) # Stores Pillar scores
    metrics_json = Column(Text, nullable=True)         # Stores the 200 raw data points
    exec_summary = Column(Text, nullable=True)         # 200-word summary
    
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    user = relationship('User', back_populates='audits')

# --- Password Utilities ---
PBKDF2_ROUNDS = int(os.getenv('PBKDF2_ROUNDS', '310000'))

def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt}${dk.hex()}"

def verify_password(password: str, hashed: str) -> bool:
    try:
        if not hashed: return False
        parts = hashed.split('$')
        if len(parts) != 4: return False
        algo, rounds, salt, hexd = parts
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(dk.hex(), hexd)
    except Exception:
        return False
