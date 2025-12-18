import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Initialize db globally
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # 1. Database Configuration (Uses your Railway variables)
    uri = os.getenv("DATABASE_URL")
    if uri and uri.startswith("postgres://"):
        # Fix for SQLAlchemy 1.4+ requirement
        uri = uri.replace("postgres://", "postgresql://", 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = uri or "sqlite:///local.db"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    # 2. Status Route
    @app.route('/')
    def index():
        return "<h1>Throughweb Audit System Online</h1><p>Status: Connected to Database.</p>"

    # 3. Create tables using the application context
    with app.app_context():
        try:
            # Relative import of your models
            from .models import Organization, User, AuditRun
            db.create_all()
            print("INFO: Database tables verified/created.")
        except Exception as e:
            print(f"ERROR: Table creation failed: {e}")

    return app
