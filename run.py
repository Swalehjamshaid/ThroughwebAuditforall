import os
import sys

# 1. Clear the path confusion
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Point exactly to the folder containing your app.py
PROJECT_ROOT = os.path.join(BASE_DIR, 'app', 'app', 'app')
sys.path.insert(0, PROJECT_ROOT)

try:
    # We import from 'app.py' directly now that its folder is in the path
    import app as app_module
    create_app = app_module.create_app
except (ImportError, AttributeError) as e:
    print(f"Direct import failed, trying absolute path... Error: {e}")
    from app.app.app.app import create_app

flask_app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)
