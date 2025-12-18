
# run.py (at repository root /app)
import os
from app import create_app  # create_app is defined in top-level app/__init__.py

app = create_app()

if __name__ == "__main__":
       port = int(os.environ.get("PORT", 8080))
