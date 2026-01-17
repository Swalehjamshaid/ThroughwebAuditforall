
# run.py
import os
import sys
import importlib
from typing import Optional
import uvicorn


def load_app_from_target(target: str):
    """
    Load a FastAPI/Starlette `app` object from a string target like:
    - "package.module:app"
    - "module:app"
    """
    if ":" not in target:
        raise ValueError(
            f"Invalid APP_MODULE '{target}'. Use format 'module.path:attribute', e.g. 'your_package.main:app'."
        )
    module_path, attr = target.split(":", 1)
    module = importlib.import_module(module_path)
    app_obj = getattr(module, attr)
    return app_obj


def try_candidates() -> Optional[object]:
    """
    Try common locations for the FastAPI app object named `app`.
    Adjust or add more candidates if needed.
    """
    candidates = [
        "app.main:app",            # e.g., /app/main.py -> app = FastAPI(...)
        "your_package.main:app",   # replace 'your_package' with your package name if needed
        "backend.main:app",
        "src.main:app",
        "main:app",                # if main.py is importable as a module at root (package with __init__.py)
    ]
    last_err = None
    for target in candidates:
        try:
            return load_app_from_target(target)
        except Exception as e:
            last_err = e
    if last_err:
        print(f"[run.py] Could not auto-locate app. Last error: {last_err}", file=sys.stderr)
    return None


def get_app():
    """
    Resolve the app in this order:
      1) APP_MODULE env var (e.g., 'your_package.main:app')
      2) Try common candidates
    """
    app_module = os.getenv("APP_MODULE")
    if app_module:
        return load_app_from_target(app_module)

    app_obj = try_candidates()
    if app_obj is None:
        raise RuntimeError(
            "FastAPI `app` not found. Set env APP_MODULE to your module path, "
            "e.g. APP_MODULE=your_package.main:app"
        )
    return app_obj


if __name__ == "__main__":
    # Get Railway's injected PORT (fallback to 8000 for local runs)
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")  # must be 0.0.0.0 on Railway

    app = get_app()

    # Optional: Uvicorn tuning via env (safe defaults for Railway)
    reload = os.getenv("RELOAD", "false").lower() == "true"  # keep False in prod
    workers_env = os.getenv("WEB_CONCURRENCY")
    if workers_env:
        # When using multiple workers, make sure your code is worker-safe.
        uvicorn.run(app, host=host, port=port, workers=int(workers_env))
    else:
        uvicorn.run(app, host=host, port=port, reload=reload)
