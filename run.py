
# run.py

from app.app.app.app import create_app

application = create_app()  # Gunicorn uses this variable

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    application.run(host="0.0.0.0", port=port)
