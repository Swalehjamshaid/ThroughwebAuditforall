import os
import sys

# 1. Path Diagnosis: Find the absolute path to the deepest folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# This points exactly to where your app.py and models.py are
DEEP_PATH = os.path.join(BASE_DIR, 'app', 'app', 'app')

# 2. Inject this path into Python's search list
sys.path.insert(0, DEEP_PATH)

try:
    # Now Python can see 'app.py' inside the deep folder directly
    from app import create_app
    app = create_app()
except ImportError as e:
    print(f"Path Error: {e}")
    # Fallback for Gunicorn context
    from app.app.app.app import create_app
    app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
