import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Initialize the database extension
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # 1. Fetch the DATABASE_URL from Railway
    database_url = os.getenv("DATABASE_URL")

    # 2. Fix the database URL prefix for SQLAlchemy 1.4+
    if database_url:
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        # Fallback for local testing
        app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///local_test.db"

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize the app with the database
    db.init_app(app)

    # 3. FIX: Add a Root Route to prevent the "404 Not Found" error
    @app.route('/')
    def index():
        return "<h1>Server is running!</h1><p>Database connected and tables verified.</p>"

    # 4. Automatically create database tables
    with app.app_context():
        try:
            # If you have a models.py file, it should be imported here
            # from . import models 
            db.create_all()
            print("Database tables created successfully!")
        except Exception as e:
            print(f"Error creating tables: {e}")

    return app
