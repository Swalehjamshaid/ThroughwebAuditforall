import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Initialize db object
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # 1. Database Configuration
    uri = os.getenv("DATABASE_URL")
    if uri and uri.startswith("postgres://"):
        # Fix for Railway/Heroku prefix
        uri = uri.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = uri or "sqlite:///local.db"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    # 2. Prevent 404 Error
    @app.route('/')
    def home():
        return "<h1>Server is Online</h1><p>Database connected.</p>"

    # 3. Create Tables
    with app.app_context():
        try:
            from . import models
            db.create_all()
        except Exception as e:
            print(f"Table Creation Log: {e}")

    return app
