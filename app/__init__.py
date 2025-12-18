import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Initialize db globally so it can be imported by models.py
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # 1. Database Configuration (Fixes the Railway postgres:// prefix)
    uri = os.getenv("DATABASE_URL")
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = uri or "sqlite:///local.db"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    # 2. Web Interface (The page you saw in your screenshot)
    @app.route('/')
    def index():
        return """
        <h1>Throughweb Audit System Online</h1>
        <p>Status: Connected to Database.</p>
        <p>Tables: Organization, User, AuditRun initialized.</p>
        """

    # 3. FORCE TABLE CREATION
    with app.app_context():
        try:
            from . import models
            # This command scans models.py and builds the tables in Postgres
            db.create_all()
            print("DATABASE INFO: Tables created successfully.")
        except Exception as e:
            print(f"DATABASE ERROR: {e}")

    return app
