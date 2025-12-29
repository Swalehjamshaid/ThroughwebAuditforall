
#!/usr/bin/env bash
set -e

# Install dependencies
pip install --no-cache-dir -r requirements.txt

# Start the app
exec uvicorn fftech_audit.app:app --host 0.0.0.0 --port "${PORT:-8080}"
