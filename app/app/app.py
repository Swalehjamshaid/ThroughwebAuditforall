import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # Database Configuration (Fixed for Railway)
    uri = os.getenv("DATABASE_URL")
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = uri or "sqlite:///local.db"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    # Prevent 404
    @app.route('/')
    def index():
        return "<h1>Throughweb Audit System Online</h1>"

    # Create Tables automatically
    with app.app_context():
        try:
            from . import models
            db.create_all()
        except Exception as e:
            print(f"DB Sync log: {e}")

    return app
