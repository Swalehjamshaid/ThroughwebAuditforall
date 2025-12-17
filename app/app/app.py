import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Initialize the db object
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # 1. Fetch the DATABASE_URL provided by Railway
    database_url = os.getenv("DATABASE_URL")

    # 2. Fix the database URL and handle the missing variable
    if database_url:
        # Railway/Heroku provide 'postgres://', but SQLAlchemy 1.4+ requires 'postgresql://'
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        print("Successfully found DATABASE_URL. Connecting to Postgres...")
    else:
        # Fallback if the variable is not linked yet
        app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///local_test.db"
        print("CRITICAL: DATABASE_URL not found. Using local SQLite.")

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize the extension
    db.init_app(app)

    # 3. FIX: Add a Root Route to stop the 404 error
    @app.route('/')
    def home():
        return "<h1>Server is Up!</h1><p>Connected to database successfully.</p>"

    # 4. Create database tables automatically
    with app.app_context():
        try:
            # Important: This ensures your tables appear in Railway
            db.create_all()
            print("Database tables verified/created.")
        except Exception as e:
            print(f"Error during table creation: {e}")

    return app
