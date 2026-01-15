import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .db import init_db
from . import auth, audits, reports, schedule

app = FastAPI(title=os.getenv('BRAND_NAME','FF Tech') + ' AI Website Audit API')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

BASE_DIR = os.path.dirname(__file__)
app.mount('/static', StaticFiles(directory=os.path.join(BASE_DIR, 'static')), name='static')
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, 'templates'))

app.include_router(auth.router, prefix='/api/auth', tags=['auth'])
app.include_router(audits.router, prefix='/api', tags=['audits'])
app.include_router(reports.router, prefix='/api', tags=['reports'])
app.include_router(schedule.router, prefix='/api', tags=['schedule'])

@app.on_event('startup')
async def startup():
    init_db()

@app.get('/')
async def index(request: Request):
    return templates.TemplateResponse('index.html', {'request': request, 'brand': os.getenv('BRAND_NAME','FF Tech')})