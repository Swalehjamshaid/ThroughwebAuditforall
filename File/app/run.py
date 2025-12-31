
"""
Entrypoint for platforms that start the container with:
    python /app/run.py

Boots the FastAPI app at app.main:app and binds to the platform-provided PORT.
"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    # IMPORTANT: this string path must match where your FastAPI app is defined
    # i.e., FastAPI() instance named 'app' inside app/main.py
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")
