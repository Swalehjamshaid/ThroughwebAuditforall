from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os


def normalize_database_url(url: str) -> str:
    if not url or not url.strip():
        raise RuntimeError("DATABASE_URL is not set")
    url = url.strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://") and "+psycopg" not in url and "+psycopg2" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI"))
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# Dependency for FastAPI endpoints
from contextlib import contextmanager
@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
