
#!/usr/bin/env bash
set -euo pipefail

echo "Python: $(python --version 2>&1)"
echo "Working dir: $(pwd)"
ls -la

# Install dependencies from root requirements.txt
if [[ -f requirements.txt ]]; then
  echo "Installing Python requirements..."
  pip install --no-cache-dir -r requirements.txt
else
  echo "ERROR: requirements.txt not found at repo root."
  exit 1
fi

# Use Railway-provided port or default to 8080
export PORT="${PORT:-8080}"
echo "Starting Uvicorn on 0.0.0.0:${PORT}"

# Start your FastAPI app (module path inside fftech_audit/)
exec uvicorn fftech_audit.app:app --host 0.0.0.0 --port "${PORT}"
