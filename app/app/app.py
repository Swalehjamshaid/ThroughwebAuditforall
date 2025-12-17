import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Initialize the db object
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # 1. Database Connection Logic
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        # Fix for Railway/Heroku prefix requirement
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///local.db"

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    # 2. Add Routes (This prevents the 404 error)
    @app.route('/')
    def home():
        return "<h1>Throughweb Audit System</h1><p>Status: Connected to Database.</p>"

    # 3. Create Database Tables
    with app.app_context():
        try:
            # We import models here to tell SQLAlchemy what tables to create
            # Replace 'from .models import *' with your actual model file if different
            from . import models 
            db.create_all()
            print("Database tables initialized!")
        except Exception as e:
            print(f"Table creation error: {e}")

    return app
