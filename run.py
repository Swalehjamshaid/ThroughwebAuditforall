import os
from app.app.app.app import create_app

# Create the application instance
app = create_app()

if __name__ == "__main__":
    # Use the PORT provided by Railway, default to 8080
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
