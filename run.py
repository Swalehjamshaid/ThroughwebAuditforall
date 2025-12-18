import os
import sys

# 1. Standardize the root path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

# 2. Add both levels of 'app' folders to the path
# This ensures that 'from app import create_app' works regardless of nesting
sys.path.append(os.path.join(BASE_DIR, 'app'))
sys.path.append(os.path.join(BASE_DIR, 'app', 'app'))

try:
    from app.app import create_app
except ImportError:
    from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
