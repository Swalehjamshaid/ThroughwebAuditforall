
# run.py
import os
import uvicorn

# Import your FastAPI app here:
# If your app object is defined in app/main.py as `app = FastAPI(...)`, use:
from app.main import app

def main():
    # Read environment variables with safe defaults
    host = os.getenv("HOST", "0.0.0.0")
    port_str = os.getenv("PORT", "8000")
    try:
        port = int(port_str)
    except ValueError:
        # If PORT is set but invalid, fall back to 8000
        port = 8000

    # Start Uvicorn programmatically with numeric port
    uvicorn.run(app, host=host, port=port, workers=int(os.getenv("WORKERS", "1")))

if __name__ == "__main__":
    main()
