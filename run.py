import os
import sys

# 1. Get the absolute path of the directory containing run.py
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

# 2. Add the nested folder to the path so Python can find 'models' and 'create_app'
# Based on your structure: ThroughwebAuditforall/app/app/
nested_app_path = os.path.join(BASE_DIR, 'app', 'app')
sys.path.insert(0, nested_path)

# 3. Import from the correct package path
from app.app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
