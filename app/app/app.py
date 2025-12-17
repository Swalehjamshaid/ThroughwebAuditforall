import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Initialize db
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # 1. Database Configuration
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///local.db"

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    # 2. Basic Route
    @app.route('/')
    def home():
        return "<h1>Throughweb Audit App</h1><p>Database Status: Connected</p>"

    # 3. Create Tables (Crucial Step)
    with app.app_context():
        try:
            # We import the models file here so SQLAlchemy "sees" your classes
            from . import models 
            db.create_all()
            print("Successfully created tables: Organization, User, AuditRun")
        except Exception as e:
            print(f"Table Creation Log: {e}")

    return app
