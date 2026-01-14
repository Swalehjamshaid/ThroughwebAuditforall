import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings

# Access the attribute from config
DATABASE_URL = settings.DATABASE_URL

# Fix for Railway/Heroku 'postgres://' prefix
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
