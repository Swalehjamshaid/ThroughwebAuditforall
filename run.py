import os
import sys

# 1. Direct Path Injection
# This tells Python to go straight to the folder containing your app.py
base_dir = os.path.dirname(os.path.abspath(__file__))
deep_dir = os.path.join(base_dir, 'app', 'app', 'app')

if deep_dir not in sys.path:
    sys.path.insert(0, deep_dir)

try:
    # 2. We import the file 'app.py' as a module named 'backend' 
    # to avoid the 'app' folder name conflict entirely.
    import app as backend
    app = backend.create_app()
except Exception as e:
    # Fallback if names are still clashing
    print(f"Primary import failed: {e}")
    from app.app.app.app import create_app
    app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
