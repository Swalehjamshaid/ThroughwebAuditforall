
from fastapi import FastAPI, Depends, Request, HTTPException, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import jwt
from typing import Optional

from .db import Base, engine, get_db
from .models import User, Audit
from .schemas import AuditCreate, AuditResponse
from .audit.compute import audit_site_sync
from .report.report import build_pdf
from .report.record import export_png, export_xlsx, export_pptx
from .auth import router as auth_router
from .config import settings

app = FastAPI(title="FF Tech – AI Website Audit")
app.mount('/static', StaticFiles(directory='app/static'), name='static')
templates = Jinja2Templates(directory='app/templates')

# Create tables
Base.metadata.create_all(bind=engine)

app.include_router(auth_router)

JWT_ALG = "HS256"

def current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get('session')
    if not token: return None
    try:
        data = jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALG])
        uid = int(data['sub'])
        return db.query(User).get(uid)
    except Exception:
        return None

@app.get('/', response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse('index.html', {"request": request})

@app.get('/login', response_class=HTMLResponse)
async def login(request: Request):
    return templates.TemplateResponse('login.html', {"request": request})

@app.get('/verify', response_class=HTMLResponse)
async def verify_page(request: Request):
    return templates.TemplateResponse('verify.html', {"request": request})

@app.get('/dashboard', response_class=HTMLResponse)
async def dashboard(request: Request, user: User = Depends(current_user)):
    if not user:
        return HTMLResponse("<meta http-equiv='refresh' content='0; url=/login'>", status_code=200)
    return templates.TemplateResponse('dashboard.html', {"request": request, "user": user})

# Open & registered audit endpoint
@app.post('/api/audit', response_model=AuditResponse)
async def run_audit(payload: AuditCreate, request: Request, db: Session = Depends(get_db)):
    user = await current_user(request, db)  # type: ignore
    # Enforce quota for registered free users
    user_id = user.id if user else None
    if user:
        count = db.query(Audit).filter(Audit.user_id == user.id).count()
        if not user.is_paid and count >= 10:
            raise HTTPException(402, detail="Free quota exceeded. Upgrade to continue.")

    result = audit_site_sync(payload.url)
    overall = result['overall']

    audit = Audit(user_id=user_id, url=payload.url, status='completed', score=overall['score'], grade=overall['grade'], coverage=overall['coverage'], metrics=result['metrics'], summary=result['summary'])
    # For open access, do not store history
    if user:
        db.add(audit)
        db.commit()
        db.refresh(audit)
        audit_id = audit.id
    else:
        audit_id = 0

    return AuditResponse(id=audit_id, url=payload.url, score=overall['score'], grade=overall['grade'], coverage=overall['coverage'], summary=result['summary'], metrics=result['metrics'])

@app.get('/api/audit/list')
async def list_audits(request: Request, db: Session = Depends(get_db)):
    user = await current_user(request, db)  # type: ignore
    if not user:
        raise HTTPException(401, detail="Not signed in")
    items = db.query(Audit).filter(Audit.user_id == user.id).order_by(Audit.id.desc()).limit(50).all()
    return [{"id": a.id, "url": a.url, "score": a.score, "grade": a.grade, "coverage": a.coverage, "created_at": a.created_at.isoformat()} for a in items]

# Reports
# Open-access on-the-fly PDF
from fastapi import Body
from typing import Dict, Any

@app.post('/api/report/pdf-open')
async def report_pdf_open(payload: Dict[str, Any] = Body(...)):
    overall = payload.get('overall') or {'score': payload.get('score',0), 'grade': payload.get('grade','D'), 'coverage': payload.get('coverage',0)}
    metrics = payload.get('metrics') or {}
    pdf = build_pdf({"overall": overall, "metrics": metrics})
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=fftech_audit.pdf"})

@app.get('/api/report/pdf/{audit_id}')
async def report_pdf(audit_id: int, db: Session = Depends(get_db)):
    if audit_id == 0:
        raise HTTPException(404, detail="Open-access PDF can be downloaded only immediately after audit via a persisted session in future versions.")
    a = db.query(Audit).get(audit_id)
    if not a:
        raise HTTPException(404, detail="Audit not found")
    pdf = build_pdf({"overall": {"score": a.score, "grade": a.grade, "coverage": a.coverage}, "metrics": a.metrics})
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=fftech_audit_{a.id}.pdf"})

@app.get('/api/report/xlsx/{audit_id}')
async def report_xlsx(audit_id: int, db: Session = Depends(get_db)):
    a = db.query(Audit).get(audit_id)
    if not a:
        raise HTTPException(404, detail="Audit not found")
    x = export_xlsx({"metrics": a.metrics, "overall": {"score": a.score, "grade": a.grade, "coverage": a.coverage}})
    return Response(content=x, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename=fftech_audit_{a.id}.xlsx"})

@app.get('/api/report/pptx/{audit_id}')
async def report_pptx(audit_id: int, db: Session = Depends(get_db)):
    a = db.query(Audit).get(audit_id)
    if not a:
        raise HTTPException(404, detail="Audit not found")
    p = export_pptx({"metrics": a.metrics, "overall": {"score": a.score, "grade": a.grade, "coverage": a.coverage}})
    return Response(content=p, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation", headers={"Content-Disposition": f"attachment; filename=fftech_audit_{a.id}.pptx"})
