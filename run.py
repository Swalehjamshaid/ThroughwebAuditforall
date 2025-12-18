import os
import sys

# Get the absolute path of the root directory
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

# Fix: Define the variable and use it consistently
nested_app_path = os.path.join(BASE_DIR, 'app', 'app')
sys.path.insert(0, nested_app_path)

# Import the application factory
from app.app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
