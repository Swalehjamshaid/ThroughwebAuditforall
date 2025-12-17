import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # Database URL adjustment
    uri = os.getenv("DATABASE_URL")
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = uri or "sqlite:///local.db"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    @app.route('/')
    def home():
        return "<h1>Server is Up!</h1><p>Connected to database successfully.</p>"

    with app.app_context():
        try:
            # Importing models to trigger table creation
            from . import models 
            db.create_all()
            print("Tables created!")
        except Exception as e:
            print(f"Startup log: {e}")

    return app
