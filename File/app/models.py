
# app/models.py
from sqlalchemy import create_engine, Column, String, Integer, Boolean, Text, text
from sqlalchemy.orm import declarative_base, sessionmaker
from .settings import DATABASE_URL

# SQLAlchemy setup
engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
Base = declarative_base()

# ----------------------- ORM Models -----------------------
class User(Base):
    __tablename__ = 'users'
    id            = Column(Integer, primary_key=True)
    email         = Column(String, unique=True, index=True)
    name          = Column(String)                # display name
    company       = Column(String)                # company name
    role          = Column(String, default='user')
    password_hash = Column(String, nullable=False, default='')  # align with DB: NOT NULL + default ''
    verified      = Column(Boolean, default=False)

class Audit(Base):
    __tablename__ = 'audits'
    id         = Column(Integer, primary_key=True)
    user_email = Column(String, index=True)
    url        = Column(String)
    date       = Column(String)
    grade      = Column(String)
    summary    = Column(Text)

# ----------------------- Initialization -----------------------
_engine_inited = False

def init_engine():
    """Hook for future engine init steps."""
    global _engine_inited
    if not _engine_inited:
        _engine_inited = True

def create_schema():
    """
    Create tables if they do not exist, then ensure columns exist
    for Postgres. This prevents 'UndefinedColumn' and NOT NULL violations.
    """
    Base.metadata.create_all(engine)
    _ensure_user_columns()

def get_session():
    try:
        return SessionLocal()
    except Exception:
        return None

# ----------------------- Lightweight Migration -----------------------
def _ensure_user_columns():
    """
    Add (or align) columns on the 'users' table for Postgres.
    We use IF NOT EXISTS / DEFAULT to avoid errors if columns already exist.
    """
    dialect = engine.dialect.name.lower()
    if dialect != "postgresql":
        # Only run raw DDL on Postgres
        return

    ddl_statements = [
        # Add columns if missing
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS name          VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS company       VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role          VARCHAR DEFAULT 'user'",
        # Critical fix: ensure password_hash exists and has a default to satisfy NOT NULL
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR NOT NULL DEFAULT ''",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS verified      BOOLEAN DEFAULT FALSE",

        # Helpful indexes (no-op if already exist)
        "CREATE INDEX IF NOT EXISTS idx_users_email    ON users (email)",
        "CREATE INDEX IF NOT EXISTS idx_users_verified ON users (verified)"
    ]

    with engine.begin() as conn:
        for ddl in ddl_statements:
            conn.execute(text(ddl))
