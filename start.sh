
#!/usr/bin/env bash
set -euo pipefail

echo "Starting Gunicorn..."
echo "PORT=${PORT:-8080}  WORKERS=${WORKERS:-2}"

# Adjust module path if your file is at app/app/app/main.py
exec gunicorn app.app.main:app --bind 0.0.0.0:${PORT:-8080} --workers ${WORKERS:-2}
