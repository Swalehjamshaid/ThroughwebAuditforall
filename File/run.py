
# run.py
import os
import uvicorn

# If your FastAPI app object is defined in app/main.py as `app = FastAPI(...)`
from app.main import app
# If your app object lives elsewhere (e.g., fftech_audit/app.py), change to:
# from fftech_audit.app import app


def _int(value: str, default: int) -> int:
    """Convert environment string to int with a safe default."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def main() -> None:
    # Railway injects PORT; fallback to 8000 if missing/invalid
    host = os.getenv("HOST", "0.0.0.0")
    port = _int(os.getenv("PORT", "8000"), 8000)
    workers = _int(os.getenv("WORKERS", "1"), 1)

    # Start Uvicorn with numeric port (no shell expansion needed)
    uvicorn.run(app, host=host, port=port, workers=workers)


if __name__ == "__main__":
    main()
