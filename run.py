import os
import sys

# 1. Standardize pathing
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

# 2. Add EVERY possible nested folder to sys.path
# This forces Python to find your code no matter how many 'app' folders exist
path_to_logic = os.path.join(BASE_DIR, 'app', 'app', 'app', 'app')
if os.path.exists(path_to_logic):
    sys.path.insert(0, path_to_logic)

# 3. Import create_app using the internal name
try:
    # This tries to load from the deepest folder directly
    import __init__ as core
    create_app = core.create_app
except (ImportError, AttributeError):
    # Fallback to standard import if nesting changes
    from app.app.app.app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
