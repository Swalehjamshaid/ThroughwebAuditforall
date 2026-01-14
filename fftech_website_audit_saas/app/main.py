from fastapi import FastAPI
from app.database import engine, Base
from app.routers.audit_routes import router as audit_router
from app.routers.auth import router as auth_router

# Initialize Database Tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="FF Tech AI Website Audit SaaS")

# Include Routers
app.include_router(auth_router)
app.include_router(audit_router)

@app.get("/")
def root():
    return {"status": "Online", "message": "FF Tech AI Audit API is running."}
