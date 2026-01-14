import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings 

# 1. FIX: Force the connection string to use 'psycopg' (v3) 
# This stops SQLAlchemy from looking for the missing 'psycopg2'
db_url = settings.DATABASE_URL
if db_url:
    # Railway often provides 'postgres://', which SQLAlchemy 2.0+ requires as 'postgresql://'
    # We append '+psycopg' to explicitly use the version 3 driver installed in requirements.txt
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

# 2. Create the Engine
# pool_pre_ping=True helps maintain stability on Railway deployments
engine = create_engine(
    db_url, 
    pool_pre_ping=True,
    echo=False
)

# 3. Create Session and Base
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 4. FIX: Provide 'db_session' for your auth.py and routes
# This is a dependency generator that FastAPI's Depends() expects
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# IMPORTANT: Alias get_db to db_session because your auth.py 
# specifically does: "from .db import db_session"
db_session = get_db
