import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Initialize db object
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # 1. Database Configuration & Railway Fix
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        # Fix for Railway/Heroku postgres:// prefix
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///local_test.db"

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    # 2. Root Route (Prevents 404 error)
    @app.route('/')
    def home():
        return "<h1>Throughweb Audit App: Online</h1><p>Connected to Postgres.</p>"

    # 3. Automatic Table Creation
    with app.app_context():
        try:
            # We import models here to register them with SQLAlchemy
            from . import models 
            db.create_all()
            print("Successfully created all database tables.")
        except Exception as e:
            print(f"Table initialization log: {e}")

    return app
