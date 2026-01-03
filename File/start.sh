
#!/usr/bin/env bash
set -euo pipefail

# Print environment for debugging (optional)
echo "Starting Gunicorn..."
echo "PORT=${PORT:-8000}  WORKERS=${WORKERS:-2}"

# Bind to 0.0.0.0 and selected PORT
exec gunicorn app.app.main:app --bind 0.0.0.0:${PORT:-8000} --workers ${WORKERS:-2}
