import os
import sys

# Add root and both app levels to Python path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, 'app'))
sys.path.insert(0, os.path.join(BASE_DIR, 'app', 'app'))

# Try importing create_app from the deepest (real) package first
try:
    from app.app import create_app
except ImportError:
    try:
        from app import create_app
    except ImportError as e:
        raise ImportError("Cannot find create_app. Check your folder structure.") from e

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
