import os
import sys

# 1. Get the absolute path to the deepest folder where app.py lives
# This points to /app/app/app/ inside your container
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEEP_CODE_DIR = os.path.join(BASE_DIR, 'app', 'app', 'app')

# 2. Add this path to the very top of Python's search list
sys.path.insert(0, DEEP_CODE_DIR)

try:
    # Now that the path is set, Python can find 'app.py' directly
    from app import create_app
    app = create_app()
except ImportError as e:
    print(f"Path Injection failed: {e}")
    # Final fallback attempt
    from app.app.app.app import create_app
    app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
