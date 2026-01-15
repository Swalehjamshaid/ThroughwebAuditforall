from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
import logging

from .config import settings
from .database import Base, engine          # ← THIS IS THE FIXED LINE
from .models import *  # noqa
from .auth import router as auth_router
from .routers.audit_routes import router as audit_router
from .routers.user_routes import router as user_router

app = FastAPI(title=f"{settings.UI_BRAND_NAME} — AI Website Audit")

# ... rest of the file remains unchanged
