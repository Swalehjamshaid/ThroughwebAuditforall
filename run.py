import os
import sys

# 1. Map out the deep path where your actual app.py is
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Points exactly to the internal folder
CODE_DIR = os.path.join(BASE_DIR, 'app', 'app', 'app')

# 2. Force Python to prioritize this folder
sys.path.insert(0, CODE_DIR)

try:
    # We import the file 'app.py' as 'main_module' to avoid naming conflicts
    import app as main_module
    # Use getattr to safely find the function
    create_app_func = getattr(main_module, 'create_app', None)
    
    if create_app_func:
        app = create_app_func()
    else:
        # Emergency fallback if attributes are still masked
        from app import create_app
        app = create_app()

except Exception as e:
    print(f"Path recovery failed: {e}")
    # Final manual attempt
    sys.path.append(BASE_DIR)
    from app.app.app.app import create_app
    app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
