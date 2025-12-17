import os
import sys

# This tells Python to treat the deep nested folder as the starting point
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, 'app', 'app', 'app'))

try:
    # This tries to import it after we added the path
    from app import create_app
except ImportError:
    # Fallback import
    from app.app.app.app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
