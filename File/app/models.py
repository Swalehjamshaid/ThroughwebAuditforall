
# app/models.py
from sqlalchemy import create_engine, Column, String, Integer, Boolean, Text, text
from sqlalchemy.orm import declarative_base, sessionmaker
from .settings import DATABASE_URL

# Create engine and session factory
engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
Base = declarative_base()

# ----------------------- ORM Models -----------------------
class User(Base):
    __tablename__ = 'users'
    id       = Column(Integer, primary_key=True)
    email    = Column(String, unique=True, index=True)
    name     = Column(String)         # display name
    company  = Column(String)         # company name
    role     = Column(String, default='user')
    password = Column(String, nullable=True)
    verified = Column(Boolean, default=False)

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
    """Mark engine initialized (hook for future init steps)."""
    global _engine_inited
    if not _engine_inited:
        _engine_inited = True

def create_schema():
    """
    Create tables if they do not exist, then ensure the users table
    has all expected columns (Postgres-safe).
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
    Add any missing columns on the 'users' table, but only for Postgres.
    SQLAlchemy's create_all() does not ALTER existing tables, so we
    run raw DDL statements using IF NOT EXISTS.

    For other backends (e.g., SQLite), you might prefer Alembic or
    explicit migration scripts; here we focus on the Postgres case
    because your error stack shows psycopg2 (Postgres driver).
    """
    dialect = engine.dialect.name.lower()
    if dialect != "postgresql":
        # No-op for non-Postgres backends (avoid dialect differences).
        return

    ddl_statements = [
        # Add columns if missing
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS name     VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS company  VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role     VARCHAR DEFAULT 'user'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password VARCHAR NULL",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS verified BOOLEAN  DEFAULT FALSE",

        # Helpful indexes (no-op if they already exist)
        "CREATE INDEX IF NOT EXISTS idx_users_email    ON users (email)",
        "CREATE INDEX IF NOT EXISTS idx_users_verified ON users (verified)"
    ]

    with engine.begin() as conn:
        for ddl in ddl_statements:
            conn.execute(text(ddl))
