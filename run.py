import os
import sys

# This line tells Python to look inside your nested folders
sys.path.append(os.path.join(os.path.dirname(__file__), 'app', 'app', 'app'))

try:
    from app import create_app
except ImportError:
    # Fallback for different directory resolutions
    from app.app.app.app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
