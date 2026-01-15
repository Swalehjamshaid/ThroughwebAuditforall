import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from .config import settings
from .routers import audits, auth, users, reports, schedule
from .database import init_db

app = FastAPI(title=f"{settings.BRAND_NAME} AI Website Audit API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],)

static_dir = os.path.join(os.path.dirname(__file__), 'static')
app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), 'templates'))

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(audits.router, prefix="/api", tags=["audits"])
app.include_router(users.router, prefix="/api", tags=["users"])
app.include_router(reports.router, prefix="/api", tags=["reports"])
app.include_router(schedule.router, prefix="/api", tags=["schedule"])

@app.on_event("startup")
async def on_startup():
    init_db()

# UI routes to match snapshot
@app.get("/")
async def page_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "brand": settings.BRAND_NAME})

@app.get("/login")
async def page_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register")
async def page_register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/verify")
async def page_verify(request: Request):
    return templates.TemplateResponse("verify.html", {"request": request})

@app.get("/dashboard")
async def page_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/new")
async def page_new_audit(request: Request):
    return templates.TemplateResponse("new_audit.html", {"request": request})

@app.get("/admin")
async def page_admin(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})