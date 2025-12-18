
import os
from app import create_app

# Create the Flask application object for Gunicorn to import
app = create_app()

# Local dev only. Under Gunicorn, this block is ignored.
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
