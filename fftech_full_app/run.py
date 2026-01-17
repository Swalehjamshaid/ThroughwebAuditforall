
# fftech_full_app/run.py
import os
import uvicorn

# Your FastAPI app is defined in app/main.py as "app"
from app.main import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))  # Railway injects PORT at runtime
    uvicorn.run(app, host="0.0.0.0", port=port)
