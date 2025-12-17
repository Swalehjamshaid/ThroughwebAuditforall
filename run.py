import os
import sys

# Get the absolute path to the deepest folder where app.py actually lives
# This tells Python to look directly at your code first
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEEP_CODE_DIR = os.path.join(BASE_DIR, 'app', 'app', 'app')
sys.path.insert(0, DEEP_CODE_DIR)

try:
    # Now that we've added the path, we can import 'app.py' directly
    import app as app_module
    flask_app = app_module.create_app()
except Exception as e:
    print(f"Import failed: {e}")
    # Final safety fallback
    from app.app.app.app import create_app
    flask_app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)
