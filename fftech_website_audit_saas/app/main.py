
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .db import init_db
from .routers import pages, api, auth
from .config import settings

app = FastAPI(title=f"{settings.BRAND_NAME} AI Website Audit")
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

app.mount('/static', StaticFiles(directory='app/static'), name='static')

app.include_router(pages.router)
app.include_router(auth.router, prefix='/auth', tags=['auth'])
app.include_router(api.router, prefix='/api', tags=['api'])

@app.on_event('startup')
async def startup():
    init_db()
