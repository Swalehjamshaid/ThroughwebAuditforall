import os
import sys

# Standardize pathing for Railway
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

from app import create_app

app = create_app()

if __name__ == "__main__":
    # Use the port assigned by Railway
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
