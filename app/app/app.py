import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# 1. Initialize the db object outside the factory
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # 2. Database Connectivity & Variable Adjustment
    # This grabs the DATABASE_URL you linked in your Railway variables
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        # FIX: Railway/Heroku provide 'postgres://', but SQLAlchemy 1.4+ 
        # requires 'postgresql://'. This adjustment fixes the 'Could not parse' error.
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        print("INFO: Connected to PostgreSQL successfully.")
    else:
        # Fallback to local SQLite for development if DATABASE_URL is missing
        app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///local_test.db"
        print("WARNING: DATABASE_URL not found. Using local SQLite.")

    # Standard configuration to optimize performance
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # 3. Initialize the app with the SQLAlchemy extension
    db.init_app(app)

    # 4. FIX: Home Route (Prevents the 404 Not Found error)
    @app.route('/')
    def home():
        return """
        <h1>Throughweb Audit for All - Status: Online</h1>
        <p>Your Flask application is correctly connected to the Railway Database.</p>
        <p>Database Type: {}</p>
        """.format("PostgreSQL" if "postgresql" in app.config['SQLALCHEMY_DATABASE_URI'] else "SQLite")

    # 5. Database Table Creation Logic
    # This automatically creates your tables in the Postgres Data tab
    with app.app_context():
        try:
            # We import your models here. 
            # If your model file is named 'models.py', this will load it.
            try:
                from . import models
            except (ImportError, ValueError):
                # Fallback if the folder structure is being tricky
                import models
            
            db.create_all()
            print("INFO: Database tables verified and created successfully.")
        except Exception as e:
            print(f"ERROR: Table creation failed: {e}")

    return app
