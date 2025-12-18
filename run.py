import os
import sys

# 1. Standardize paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

# 2. Add the nested folders to sys.path
# This allows 'import auth' to work even if it's 3 levels deep
app_path = os.path.join(BASE_DIR, 'app', 'app')
if os.path.exists(app_path):
    sys.path.insert(0, app_path)

# 3. Import create_app
try:
    from app.app import create_app
except ImportError:
    from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
