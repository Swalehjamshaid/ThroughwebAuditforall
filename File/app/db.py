
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from .settings import settings
from .models import Base
import os
_db_url = settings.DATABASE_URL or f"sqlite+pysqlite:///{os.path.join(os.path.dirname(__file__), 'data.db')}"
_engine_args = {"pool_pre_ping": True} if settings.DATABASE_URL else {"connect_args": {"check_same_thread": False}}
engine = create_engine(_db_url, **_engine_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def db_ok() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
