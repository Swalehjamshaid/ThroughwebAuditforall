from fastapi import FastAPI
from app.database import engine, Base
from app.routers.audit_routes import router as audit_router
from app.routers.auth import router as auth_router
from app.scheduler import scheduler 

# 1. Initialize DB Tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="FF Tech AI Website Audit SaaS")

# 2. Start Background Scheduler
if not scheduler.running:
    scheduler.start()

# 3. Include Routers
app.include_router(auth_router)
app.include_router(audit_router)

@app.get("/")
def health_check():
    return {
        "status": "Online",
        "brand": "FF Tech AI",
        "scheduler_active": scheduler.running
    }
