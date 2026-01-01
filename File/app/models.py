from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
# FIXED RELATIVE IMPORTS
from .settings import DATABASE_URL, ADMIN_EMAIL, ADMIN_PASSWORD
from .security import load, save
import os

Base = declarative_base()
engine=None
SessionLocal=None

class User(Base):
    __tablename__='users'
    id=Column(Integer, primary_key=True)
    email=Column(String(255), unique=True, nullable=False)
    name=Column(String(255))
    company=Column(String(255))
    role=Column(String(50), default='user')
    password=Column(String(255))
    verified=Column(Boolean, default=False)

class Audit(Base):
    __tablename__='audits'
    id=Column(Integer, primary_key=True)
    user_email=Column(String(255), index=True)
    url=Column(String(2048))
    date=Column(String(32))
    grade=Column(String(8))

def init_engine():
    global engine, SessionLocal
    if DATABASE_URL:
        url = DATABASE_URL
        if url.startswith('postgres://'): url='postgresql://'+url[len('postgres://'):]
        engine=create_engine(url, pool_pre_ping=True)
        SessionLocal=sessionmaker(bind=engine)
    else:
        engine=None; SessionLocal=None

def create_schema():
    if engine: Base.metadata.create_all(engine)

def get_session():
    return SessionLocal() if SessionLocal else None

def migrate_json_to_db(data_path):
    if not engine: return
    s=get_session()
    try:
        users_js=load(os.path.join(data_path,'users.json'))
        audits_js=load(os.path.join(data_path,'audits.json'))
        if s.query(User).count()==0:
            for u in users_js:
                s.add(User(email=u.get('email'), name=u.get('name'), company=u.get('company'), role=u.get('role','user'), password=u.get('password'), verified=u.get('verified',False)))
            s.commit()
        if s.query(Audit).count()==0:
            for a in audits_js:
                s.add(Audit(user_email=a.get('user'), url=a.get('url'), date=a.get('date'), grade=a.get('grade')))
            s.commit()
    except Exception:
        pass

def ensure_fixed_admin(data_path):
    s=get_session()
    if s:
        try:
            admin=s.query(User).filter_by(email=ADMIN_EMAIL).first()
            if not admin:
                s.add(User(email=ADMIN_EMAIL, name='Admin', company='FF Tech', role='admin', password=ADMIN_PASSWORD, verified=True)); s.commit()
            else:
                admin.role='admin'; admin.password=ADMIN_PASSWORD; admin.verified=True; s.commit()
        except Exception:
            pass
    else:
        users_file=os.path.join(data_path,'users.json')
        users=load(users_file)
        found=False
        for u in users:
            if u.get('email')==ADMIN_EMAIL:
                u['role']='admin'; u['password']=ADMIN_PASSWORD; u['verified']=True; found=True; break
        if not found:
            users.append({'email':ADMIN_EMAIL,'name':'Admin','company':'FF Tech','role':'admin','password':ADMIN_PASSWORD,'verified':True})
        save(users_file, users)
