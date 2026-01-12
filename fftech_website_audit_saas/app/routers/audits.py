
from __future__ import annotations
import json
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta

from ..db import get_db
from ..models import User, Audit
from .auth import get_current_user, require_user
from ..audit_engine import run_audit

router = APIRouter()
TZ_OFFSET = timezone(timedelta(hours=5))

@router.get('/audits', response_class=HTMLResponse)
async def audits_page(request: Request, db: Session = Depends(get_db), user: User | None = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication required')
    audits = db.query(Audit).filter(Audit.user_id == user.id).order_by(Audit.created_at.desc()).all()
    rows = [{
        'id': a.id, 'title': a.url, 'owner': user.email, 'status': 'Complete',
        'risk': json.loads(a.result_json).get('overall_score', 0),
        'updated': a.created_at.strftime('%Y-%m-%d')
    } for a in audits]
    charts = json.loads(audits[0].result_json)['charts'] if audits else {
        'trend': {'labels': ['Jan','Feb','Mar','Apr','May','Jun'], 'values': [4,6,3,8,7,9]},
        'severity': {'labels': ['Critical','High','Medium','Low'], 'values': [5,12,20,8]},
        'top_owners': {'labels': ['Ops','IT','Finance','HR'], 'values': [22,18,12,9]},
    }
    ctx = {
        'kpis': {'audits_this_month': len(audits), 'closed_findings': 34, 'high_risk': 7, 'mean_closure_days': 9},
        'recent_audits': rows,
        'charts': charts,
    }
    return request.app.state.templates.TemplateResponse('dashboard.html', {'request': request, **ctx, 'year': request.app.state.year})

@router.post('/audits', response_class=HTMLResponse)
async def create_audit(request: Request, url: str = Form(...), db: Session = Depends(get_db), user: User | None = Depends(get_current_user)):
    user = require_user(user)
    if (user.audits_count or 0) >= 10:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail='Free tier limit reached')
    result = run_audit(url)
    audit = Audit(url=url, result_json=json.dumps(result), user_id=user.id)
    db.add(audit)
    user.audits_count = (user.audits_count or 0) + 1
    db.commit()
    ctx = {
        'audit': {'title': f'Audit: {url}', 'owner': user.email, 'status': 'Complete', 'risk': result['overall_score'], 'updated': datetime.now(TZ_OFFSET).strftime('%Y-%m-%d')},
        'findings': [{'id':'RU-01','title':'Duplicate headings','severity':'Medium','status':'Open','owner':'SEO','due':'-'}, {'id':'RU-02','title':'Uncompressed images','severity':'High','status':'Open','owner':'Ops','due':'-'}],
        'charts': result['charts'],
    }
    return request.app.state.templates.TemplateResponse('audit_detail.html', {'request': request, **ctx, 'year': request.app.state.year})
