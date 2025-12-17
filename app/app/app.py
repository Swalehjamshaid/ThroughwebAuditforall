import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # Fix the Railway DATABASE_URL prefix
    uri = os.getenv("DATABASE_URL")
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = uri or "sqlite:///local.db"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    # Root route to stop 404
    @app.route('/')
    def home():
        return "<h1>Throughweb Audit Status: Online</h1>"

    # Auto-create tables (Organization, User, AuditRun)
    with app.app_context():
        try:
            from . import models
            db.create_all()
        except Exception as e:
            print(f"DB Sync Log: {e}")

    return app
