import os
import sys

# 1. Get the absolute path of the root directory
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

# 2. Path to the FIRST 'app' folder
first_app_level = os.path.join(BASE_DIR, 'app')
sys.path.insert(0, first_app_level)

# 3. Path to the SECOND 'app' folder (where __init__.py and models.py live)
second_app_level = os.path.join(first_app_level, 'app')
sys.path.insert(0, second_app_level)

# Now, we try to import create_app. 
# Depending on your specific Git upload, one of these WILL work.
try:
    from app import create_app
except ImportError:
    try:
        from app.app import create_app
    except ImportError:
        # Emergency fallback for nested structures
        import app
        create_app = app.create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
