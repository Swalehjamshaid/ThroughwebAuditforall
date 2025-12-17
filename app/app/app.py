import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Initialize the db object
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # 1. Fetch the DATABASE_URL provided by Railway
    database_url = os.getenv("DATABASE_URL")

    # 2. Check if the URL exists and fix the prefix
    if database_url:
        # Railway/Heroku provide 'postgres://', but SQLAlchemy requires 'postgresql://'
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        # Fallback to local SQLite if no database is linked (useful for local testing)
        app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///local_test.db"
        print("Warning: DATABASE_URL not found. Using local SQLite.")

    # 3. Standard Flask-SQLAlchemy settings
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize the app with the extension
    db.init_app(app)

    # Import and register blueprints/routes here to avoid circular imports
    # from .routes import main as main_blueprint
    # app.register_blueprint(main_blueprint)

    return app
