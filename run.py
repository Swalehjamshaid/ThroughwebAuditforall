import os
import sys

# 1. Get the absolute path of the project root
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

# 2. Add all potential nested app directories to sys.path
# This ensures that 'from app import create_app' works no matter what
potential_paths = [
    os.path.join(BASE_DIR, 'app'),
    os.path.join(BASE_DIR, 'app', 'app'),
    os.path.join(BASE_DIR, 'app', 'app', 'app')
]

for path in potential_paths:
    if os.path.exists(path):
        sys.path.insert(0, path)

# 3. Flexible Import Logic
try:
    # Try direct import first
    from app import create_app
except ImportError:
    try:
        # Try nested import
        from app.app import create_app
    except ImportError:
        # Final fallback: manually find the function
        import importlib
        spec = importlib.util.spec_from_file_location("app_pkg", os.path.join(BASE_DIR, "app/app/__init__.py"))
        app_pkg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(app_pkg)
        create_app = app_pkg.create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
