
# app/models.py

from sqlalchemy import Column, Integer, String, Boolean
# IMPORTANT: import Base from your existing db.py so all models share the same metadata
from app.db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)

    # Map Python attribute 'hashed_password' to the actual DB column name.
    # If your DB column is 'password', change "password_hash" to "password".
    hashed_password = Column("password_hash", String, nullable=False)

    is_admin = Column(Boolean, default=False, nullable=False)
    audits_count = Column(Integer, default=0, nullable=False)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"
``
