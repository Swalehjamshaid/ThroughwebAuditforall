
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
import logging

from .config import settings
from .db import Base, engine
from .models import *  # noqa
from .auth import router as auth_router
from .routers.audit_routes import router as audit_router
from .routers.user_routes import router as user_router

app = FastAPI(title=f"{settings.UI_BRAND_NAME} — AI Website Audit")
app.mount('/static', StaticFiles(directory='app/static'), name='static')
templates = Jinja2Templates(directory='app/templates')
# expose brand_name globally
templates.env.globals['brand_name'] = settings.UI_BRAND_NAME

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, logging.INFO))

Base.metadata.create_all(bind=engine)

app.include_router(auth_router)
app.include_router(audit_router)
app.include_router(user_router)

@app.get('/health')
def health():
    return {'ok': True}

@app.get('/', response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse('index.html', {'request': request})
