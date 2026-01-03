
#!/usr/bin/env bash
set -euo pipefail

echo "Starting Gunicorn..."
echo "PORT=${PORT:-8080}  WORKERS=${WORKERS:-1}"

# If your main.py path is app/app/app/main.py, change the module to app.app.app.main:app
exec gunicorn app.app.main:app --bind 0.0.0.0:${PORT:-8080} --workers ${WORKERS:-1}
