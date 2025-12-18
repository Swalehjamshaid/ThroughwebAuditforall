import os
import sys

# Ensure the root directory is in the path so 'app' is recognized as a package
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

try:
    # This looks into the app/ folder and runs __init__.py
    from app import create_app
    app = create_app()
except ImportError as e:
    print(f"Import Error: {e}")
    # Fallback to absolute pathing
    from app.app.app import create_app
    app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
