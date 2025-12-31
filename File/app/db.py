
# app/db.py
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from .settings import settings
from .models import Base
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("db")

def _coerce_db_url(url: str) -> str:
    """
    Normalize Postgres URLs to use the SQLAlchemy 2.0 psycopg driver.
    Examples:
      postgres://user:pass@host:5432/db  -> postgresql+psycopg://user:pass@host:5432/db
      postgresql://user:pass@host/db     -> postgresql+psycopg://user:pass@host/db
    """
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

def _sqlite_url() -> str:
    # Place SQLite file inside the app folder
    db_path = os.path.join(os.path.dirname(__file__), "data.db")
    return f"sqlite+pysqlite:///{db_path}"

def _make_engine(url: str):
    """
    Create an engine with appropriate args for the chosen driver.
    """
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    # For network DBs (Postgres), enable pool_pre_ping to auto-drop stale connections.
    return create_engine(url, pool_pre_ping=True)

def _test_connect(engine) -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.warning("DB connection test failed: %s", e)
        return False

def _resolve_engine():
    """
    Try DATABASE_URL first; if unreachable, fall back to SQLite.
    """
    db_url_env = settings.DATABASE_URL.strip() if settings.DATABASE_URL else ""
    if db_url_env:
        url = _coerce_db_url(db_url_env)
        pg_engine = _make_engine(url)
        if _test_connect(pg_engine):
            logger.info("Connected to Postgres via DATABASE_URL.")
            return pg_engine
        else:
            logger.warning("Postgres unreachable; falling back to SQLite.")
    # Fallback
    sqlite_engine = _make_engine(_sqlite_url())
    if _test_connect(sqlite_engine):
        logger.info("Using SQLite fallback (data.db).")
        return sqlite_engine
    # As a guard: if even SQLite fails, raise (very unlikely).
    raise RuntimeError("Failed to initialize any database engine (Postgres & SQLite).")

# Resolve and expose engine + SessionLocal
engine = _resolve_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db() -> None:
    Base.metadata.create_all(bind=engine)

def db_ok() -> bool:
    return _test_connect(engine)
