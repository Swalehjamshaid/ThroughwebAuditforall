import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # Database URL adjustment for Railway
    uri = os.getenv("DATABASE_URL")
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = uri or "sqlite:///local.db"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    @app.route('/')
    def home():
        return "<h1>Throughweb Audit App is Online</h1>"

    with app.app_context():
        try:
            # This triggers your models.py to create the Postgres tables
            from . import models
            db.create_all()
        except Exception as e:
            print(f"Startup DB log: {e}")

    return app
