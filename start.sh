
# start.sh
#!/usr/bin/env sh
set -e

# Use platform-provided PORT or default to 8080
PORT="${PORT:-8080}"

exec uvicorn fftech_audit.app:app --host 0.0.0.0 --port "$PORT"
