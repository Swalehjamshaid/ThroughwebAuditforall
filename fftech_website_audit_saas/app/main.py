from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.database import engine, Base
from app.routers.audit_routes import router as audit_router
from app.routers.auth import router as auth_router
from app.scheduler import scheduler 

# Initialize Database Tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="FF Tech AI Audit SaaS")

# Mount Static and Templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Start Background Scheduler
if not scheduler.running:
    scheduler.start()

# Mount Routers
app.include_router(auth_router)
app.include_router(audit_router)

# serve the full website
@app.get("/")
async def serve_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
