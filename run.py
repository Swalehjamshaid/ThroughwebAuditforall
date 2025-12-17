import os
import sys

# 1. Identify the absolute path to the deepest folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# This points exactly to where your app.py lives
CODE_LOC = os.path.join(BASE_DIR, 'app', 'app', 'app')

# 2. Add it to the front of the path
sys.path.insert(0, CODE_LOC)

try:
    # IMPORTANT: We import the FILE 'app.py' as a unique name 'myapp'
    # to stop Python from looking at the 'app/' folder.
    import app as myapp_module
    app = myapp_module.create_app()
except Exception as e:
    print(f"Direct file import failed: {e}")
    # Fallback only
    from app.app.app.app import create_app
    app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
