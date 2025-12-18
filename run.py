import os
import sys

# Standardize pathing for the root
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

# Add the nested logic folder so 'models' and 'auth' can be found
nested_app_path = os.path.join(BASE_DIR, 'app', 'app')
sys.path.insert(0, nested_app_path)

from app.app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
