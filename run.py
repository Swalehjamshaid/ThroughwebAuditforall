import os
import sys

# 1. Force Python to see the deep nested folder
# This points to /app/app/app/app/ inside the Railway container
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEEP_DIR = os.path.join(BASE_DIR, 'app', 'app', 'app')
sys.path.insert(0, DEEP_DIR)

# 2. Import the factory
try:
    from app import create_app
except ImportError:
    # Fallback for local/different environments
    from app.app.app.app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
