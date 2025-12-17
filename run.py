import os
import sys

# 1. Force Python to look in the deepest 'app' folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEEP_PATH = os.path.join(BASE_DIR, 'app', 'app', 'app')
sys.path.insert(0, DEEP_PATH)

# 2. Import and create the app
try:
    # After shifting the path, 'app' now refers to the file 'app.py' inside the deep folder
    from app import create_app
    app = create_app()
except Exception as e:
    print(f"CRITICAL: Path error. Details: {e}")
    # Final backup attempt
    from app.app.app.app import create_app
    app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
