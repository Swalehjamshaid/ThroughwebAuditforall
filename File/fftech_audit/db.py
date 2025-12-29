
# fftech_audit/db.py

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=True)
    # IMPORTANT: map to the column that actually exists in DB
    is_verified = Column(Boolean, default=False, nullable=False)  # <-- DB column
    plan = Column(String, default="free", nullable=False)
    audits_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime)

    # Keep existing code that uses `user.verified` working
    @hybrid_property
    def verified(self) -> bool:
        return bool(self.is_verified)

    @verified.setter
    def verified(self, v: bool):
        self.is_verified = bool(v)

    @verified.expression
    def verified(cls):
        # allow filtering e.g. .filter(User.verified == True)
        return cls.is_verified
