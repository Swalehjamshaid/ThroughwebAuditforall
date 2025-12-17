import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Initialize db globally
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # 1. Use the DATABASE_URL variable from your Railway settings
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        # SQLAlchemy 1.4+ requires 'postgresql://' instead of 'postgres://'
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        # Fallback for local testing
        app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///local.db"

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # 2. Initialize extension
    db.init_app(app)

    # 3. Add a root route to stop the 404 error
    @app.route('/')
    def index():
        return "<h1>Throughweb Audit System Online</h1><p>Connected to PostgreSQL.</p>"

    # 4. Sync Database Tables
    with app.app_context():
        try:
            # Important: Importing models here so db.create_all() sees them
            from . import models
            db.create_all()
            print("PostgreSQL Tables Synced Successfully.")
        except Exception as e:
            print(f"Database sync log: {e}")

    return app
