import os
import sys

# Get the absolute path of the directory containing run.py
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

# Also add the app folder to the path for extra safety
app_path = os.path.join(BASE_DIR, 'app')
sys.path.insert(0, app_path)

try:
    from app import create_app
    app = create_app()
except ImportError as e:
    # Fallback for different environment configurations
    print(f"Primary import failed, trying absolute import: {e}")
    from app.app import create_app
    app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
