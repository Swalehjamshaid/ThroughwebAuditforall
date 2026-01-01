
from sqlalchemy import create_engine, Column, String, Integer, Boolean, Date, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from .settings import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True)
    name = Column(String)
    company = Column(String)
    role = Column(String, default='user')
    password = Column(String, nullable=True)
    verified = Column(Boolean, default=False)

class Audit(Base):
    __tablename__ = 'audits'
    id = Column(Integer, primary_key=True)
    user_email = Column(String, index=True)
    url = Column(String)
    date = Column(String)
    grade = Column(String)
    summary = Column(Text)

_engine_inited = False

def init_engine():
    global _engine_inited
    if not _engine_inited:
        _engine_inited = True

def create_schema():
    Base.metadata.create_all(engine)

def get_session():
    try:
        return SessionLocal()
    except Exception:
        return None
