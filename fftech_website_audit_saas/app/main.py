
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import settings
from .db import init_db
from . import auth, audits, users, reports, schedule

app = FastAPI(title=f"{settings.BRAND_NAME} AI Website Audit API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = os.path.join(os.path.dirname(__file__), 'static')
app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), 'templates'))

# Routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(audits.router, prefix="/api", tags=["audits"])
app.include_router(users.router, prefix="/api", tags=["users"])
app.include_router(reports.router, prefix="/api", tags=["reports"])
app.include_router(schedule.router, prefix="/api", tags=["schedule"])

@app.on_event("startup")
async def on_startup():
    init_db()

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "brand": settings.BRAND_NAME})
