import os
import sys

# Get the absolute path to the folder containing this file (run.py)
basedir = os.path.abspath(os.path.dirname(__file__))

# Add the deep nested path to the Python path
# This allows 'from app import create_app' to work
sys.path.append(os.path.join(basedir, 'app', 'app', 'app'))

try:
    # Try to import from the added path
    from app import create_app
except ImportError:
    # Backup import if the above fails
    from app.app.app.app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
