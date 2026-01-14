from fastapi import FastAPI
from app.database import engine, Base
from app.routers.audit_routes import router as audit_router
from app.routers.auth import router as auth_router
from app.scheduler import scheduler  # Ensure scheduler starts with the app

# Build database tables according to models
Base.metadata.create_all(bind=engine)

app = FastAPI(title="FF Tech AI Website Audit SaaS")

# Mount Routers using absolute paths to avoid top-level package errors
app.include_router(auth_router)
app.include_router(audit_router)

@app.get("/")
def health_check():
    return {
        "status": "Online",
        "brand": "FF Tech AI",
        "scheduler_active": scheduler.running
    }
