import os
import sys

# Get the absolute path of the project root
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

# Add the nested folders to the Python path so 'models' can be found
# Path: /app/app/
nested_path = os.path.join(BASE_DIR, 'app', 'app')
sys.path.insert(0, nested_path)

from app.app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
