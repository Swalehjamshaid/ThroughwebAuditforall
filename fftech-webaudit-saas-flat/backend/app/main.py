from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse

from .routers import audits

app = FastAPI(title="FF Tech WebAudit SaaS")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True)
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"]) 
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})

app.include_router(audits.router, prefix="/audits", tags=["audits"])

@app.get('/health')
async def health():
    return {"status":"ok"}
