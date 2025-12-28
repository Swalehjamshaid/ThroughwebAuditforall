
#!/usr/bin/env bash
set -euo pipefail

# Show environment info (optional for debugging)
echo "Python version: $(python --version 2>&1)"
echo "Working directory: $(pwd)"
echo "Listing files:"
ls -la

# Install Python dependencies from root requirements.txt
if [[ -f requirements.txt ]]; then
  echo "Installing python requirements..."
  pip install --no-cache-dir -r requirements.txt
else
  echo "ERROR: requirements.txt not found at repo root."
  exit 1
fi

# Tell user what PORT we're going to use
export PORT="${PORT:-8080}"
echo "Starting Uvicorn on 0.0.0.0:${PORT}"

# Start FastAPI app located in fftech_audit/app.py (module fftech_audit.app:app)
exec uvicorn fftech_audit.app:app --host 0.0.0.0 --port "${PORT}"
