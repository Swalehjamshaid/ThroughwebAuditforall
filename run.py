import os
import sys

# Get the absolute path of the root directory
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

# Force Python to look into the nested 'app/app' folder
nested_logic_path = os.path.join(BASE_DIR, 'app', 'app')
if os.path.exists(nested_logic_path):
    sys.path.insert(0, nested_logic_path)

# Try flexible imports to catch the create_app function
try:
    from app.app import create_app
except ImportError:
    try:
        from app import create_app
    except ImportError:
        # Final fallback: manual discovery
        import importlib.util
        init_path = os.path.join(nested_logic_path, "__init__.py")
        spec = importlib.util.spec_from_file_location("app", init_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        create_app = module.create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
