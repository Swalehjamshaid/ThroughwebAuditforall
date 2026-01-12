
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

from .db import engine, Base
from .routers import health, auth, audits, pages

app = FastAPI(title="FF Tech AI Website Audit SaaS", version="1.0.0")
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "year": datetime.utcnow().year})

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(audits.router)
app.include_router(pages.router)
