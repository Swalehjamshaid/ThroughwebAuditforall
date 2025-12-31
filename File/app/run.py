
"""
Entrypoint for Railway when it runs:
    python /app/run.py
This starts the FastAPI app defined in app/main.py.
"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    # IMPORTANT: Ensure your FastAPI app is at app.main:app
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")
