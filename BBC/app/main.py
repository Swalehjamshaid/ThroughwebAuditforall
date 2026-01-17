from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from .database import Base, engine
from .routers.audits import router as audit_router
from .routers.competitor import router as competitor_router
from .routers.admin import router as admin_router
from .auth import router as auth_router
from .config import get_settings

app = FastAPI(title='FF Tech Website Audit SaaS — PRO')
Base.metadata.create_all(bind=engine)

app.mount('/static', StaticFiles(directory='static'), name='static')
templates = Jinja2Templates(directory='templates')

settings = get_settings()
if settings.ENABLE_SCHEDULER:
    try:
        from . import scheduler as _sched
        _sched.start()
    except Exception as e:
        print('[Scheduler] failed:', e)

app.include_router(auth_router)
app.include_router(audit_router)
app.include_router(competitor_router)
app.include_router(admin_router)

@app.get('/', response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse('index.html', {'request': request})
