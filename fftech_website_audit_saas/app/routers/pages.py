
from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import User, Audit

router = APIRouter()

T = Jinja2Templates(directory='app/templates')

def get_db():
    db = SessionLocal();
    try: yield db
    finally: db.close()

@router.get('/')
async def index(request: Request):
    return T.TemplateResponse('index.html', {'request': request})

@router.get('/login')
async def login(request: Request):
    return T.TemplateResponse('login.html', {'request': request})

@router.get('/register')
async def register(request: Request):
    return T.TemplateResponse('register.html', {'request': request})

@router.get('/verify')
async def verify_page(request: Request):
    return T.TemplateResponse('verify.html', {'request': request})

@router.get('/dashboard')
async def dashboard(request: Request, db: Session = Depends(get_db)):
    audits = db.query(Audit).order_by(Audit.created_at.desc()).limit(20).all()
    return T.TemplateResponse('dashboard.html', {'request': request, 'audits': audits})

@router.get('/new_audit')
async def new_audit(request: Request):
    return T.TemplateResponse('new_audit.html', {'request': request})

@router.get('/audit_detail/{audit_id}')
async def audit_detail(audit_id: int, request: Request, db: Session = Depends(get_db)):
    a = db.query(Audit).filter(Audit.id==audit_id).first()
    return T.TemplateResponse('audit_detail.html', {'request': request, 'audit': a})

@router.get('/audit_detail_open')
async def audit_detail_open(request: Request):
    return T.TemplateResponse('audit_detail_open.html', {'request': request})

@router.get('/upgrade')
async def upgrade(request: Request):
    return T.TemplateResponse('upgrade.html', {'request': request})

@router.get('/admin')
async def admin(request: Request):
    return T.TemplateResponse('admin.html', {'request': request})
