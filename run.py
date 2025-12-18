import os
import sys
import importlib.util

# 1. Root path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

def get_create_app():
    # This manually searches for the deepest __init__.py containing your app
    for root, dirs, files in os.walk(BASE_DIR):
        if "__init__.py" in files:
            full_path = os.path.join(root, "__init__.py")
            with open(full_path, 'r', errors='ignore') as f:
                content = f.read()
                if 'def create_app' in content:
                    # Found it! Add this folder to Python's memory
                    sys.path.insert(0, root)
                    spec = importlib.util.spec_from_file_location("app_core", full_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    return module.create_app()
    return None

app = get_create_app()

if __name__ == "__main__":
    if app:
        port = int(os.environ.get("PORT", 8080))
        app.run(host="0.0.0.0", port=port)
    else:
        print("CRITICAL ERROR: Could not find create_app function in any folder.")
