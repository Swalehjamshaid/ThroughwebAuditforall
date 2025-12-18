import os
import sys

# 1. Get the absolute path of the root directory
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

# 2. Add ALL levels of 'app' to the path to ensure Python finds the logic
# This handles: Root -> app -> app -> app
level1 = os.path.join(BASE_DIR, 'app')
level2 = os.path.join(level1, 'app')
level3 = os.path.join(level2, 'app')

for path in [level1, level2, level3]:
    if os.path.exists(path):
        sys.path.insert(0, path)

# 3. Import the app factory
try:
    # We look for the folder that contains __init__.py with create_app
    from app.app import create_app
except ImportError:
    from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
