
from fastapi import FastAPI
from app.core.config import settings
from app.api.routes_audit import router as audit_router
from app.api.routes_auth import router as auth_router
from app.middleware.auth import auth_middleware
from app.db.session import engine
from app.db.models import Base
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

app = FastAPI(title=settings.APP_NAME)

@app.middleware("http")
async def _auth(request, call_next):
    return await auth_middleware(request, call_next)

# create tables only if explicitly enabled via env in real run (here always false)
import os
if os.getenv('USE_CREATE_ALL','false').lower() == 'true':
    Base.metadata.create_all(bind=engine)

app.include_router(audit_router, prefix="", tags=["audit"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])

# Web UI
app.mount("/web", StaticFiles(directory="app/web"), name="web")

@app.get("/ui")
async def ui():
    return FileResponse("app/web/index.html")

@app.get("/")
def root():
    return {"message": f"Hello from {settings.APP_NAME}", "version": "0.2.0"}

@app.get("/healthz")
def health():
    return {"status": "ok"}
