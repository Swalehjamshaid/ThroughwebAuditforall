
#!/usr/bin/env sh
set -e

# If the platform doesn't provide PORT, default to 8080
PORT="${PORT:-8080}"

# Start your FastAPI app
exec uvicorn fftech_audit.app:app --host 0.0.0.0 --port "$PORT"
``
