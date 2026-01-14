from fastapi import FastAPI
from app.database import engine, Base
from app.routers.audit_routes import router as audit_router
from app.routers.auth import router as auth_router

# Ensure tables are built
Base.metadata.create_all(bind=engine)

app = FastAPI(title="FF Tech AI Website Audit SaaS")

# Include Routers with absolute paths
app.include_router(auth_router)
app.include_router(audit_router)

@app.get("/")
def root():
    return {"message": "FF Tech AI Audit is Online", "version": "1.0.0"}
