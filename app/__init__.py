import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_mail import Mail

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
mail = Mail()

def create_app():
    app = Flask(__name__)

    # DATABASE FIX: Converts Railway URL for SQLAlchemy compatibility
    uri = os.getenv("DATABASE_URL")
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = uri
    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "789456123321654987")
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    # Register Blueprints (using local relative import)
    try:
        from .auth import auth as auth_blueprint
        app.register_blueprint(auth_blueprint)
    except Exception as e:
        print(f"Blueprint Error: {e}")

    # SYNC TABLES: This makes the "No Tables" message in Railway disappear
    with app.app_context():
        from . import models
        db.create_all()
        print("DATABASE SYNC: SUCCESSFUL")

    return app
