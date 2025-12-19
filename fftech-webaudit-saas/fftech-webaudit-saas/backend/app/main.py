import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse

from .routers import auth, audits, reports, admin, billing
from .database import init_db

app = FastAPI(title="FF Tech WebAudit SaaS", version="1.0.0")

# CORS
app.add_middleware(CORSMiddleware,
                   allow_origins=["*"],
                   allow_credentials=True,
                   allow_methods=["*"],
                   allow_headers=["*"],)

# Rate limiting
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])  # tune per plan
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})

# Routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(audits.router, prefix="/audits", tags=["audits"])
app.include_router(reports.router, prefix="/reports", tags=["reports"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(billing.router, prefix="/billing", tags=["billing"])

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.on_event("startup")
async def startup_event():
    init_db()
