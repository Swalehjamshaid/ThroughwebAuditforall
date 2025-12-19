import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
# For Railway Postgres, DATABASE_URL is injected automatically
# See docs: https://docs.railway.com/guides/postgresql

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from .models import Base

def init_db():
    Base.metadata.create_all(bind=engine)
