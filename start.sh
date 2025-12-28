
#!/usr/bin/env sh
set -e

# Default if PORT isn't set by platform
PORT="${PORT:-8080}"

exec uvicorn fftech_audit.app:app --host 0.0.0.0 --port "$PORT"
