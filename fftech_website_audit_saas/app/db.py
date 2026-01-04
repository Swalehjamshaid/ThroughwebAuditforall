
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Use Railway/Postgres if DATABASE_URL is provided; otherwise fall back to SQLite for local dev.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fftech_local.db")

# SQLAlchemy engine settings
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
        future=True,
    )
else:
    # Railway typically exposes a Postgres URL; psycopg2-binary driver is used.
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()
