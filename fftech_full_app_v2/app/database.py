
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Add it in Railway Variables.")

# Enable SSL if your Railway Postgres requires it:
USE_SSL = os.getenv("DB_SSL", "false").lower() == "true"
connect_args = {"sslmode": "require"} if USE_SSL else {}

engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def init_db():
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
