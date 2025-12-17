# app/__init__.py

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # Database config (Railway compatible)
    uri = os.getenv("DATABASE_URL")
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = uri or "sqlite:///local.db"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    # Test route
    @app.route('/')
    def index():
        return "<h1>Throughweb Audit System Online</h1>"

    # Create tables
    with app.app_context():
        try:
            from .models import Organization, User, AuditRun  # Explicit import
            db.create_all()
            print("Tables created: organization, user, audit_run")
        except Exception as e:
            print(f"Error creating tables: {e}")

    return app
