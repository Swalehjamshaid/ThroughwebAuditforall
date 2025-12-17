import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # Database setup with Railway-specific fixes
    uri = os.getenv("DATABASE_URL")
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = uri or "sqlite:///local.db"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    @app.route('/')
    def home():
        return "<h1>Throughweb Audit Status: Online</h1>"

    # Auto-create tables for Organization, User, and AuditRun
    with app.app_context():
        try:
            from . import models
            db.create_all()
            print("Database tables synchronized successfully.")
        except Exception as e:
            print(f"Database error on startup: {e}")

    return app
