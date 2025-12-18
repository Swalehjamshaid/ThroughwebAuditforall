import os
import sys

# 1. Get the absolute path of the root directory
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

# 2. Add the nested folders to the Python path
# Matches your structure: ThroughwebAuditforall/app/app/
first_level = os.path.join(BASE_DIR, 'app')
second_level = os.path.join(first_level, 'app')

sys.path.insert(0, first_level)
sys.path.insert(0, second_level)

# 3. Import create_app from the deepest nested package
from app.app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
