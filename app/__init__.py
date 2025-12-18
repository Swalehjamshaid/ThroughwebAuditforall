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
    # Detect the correct template folder by moving up levels
    # This reaches /app/templates from /app/app/__init__.py
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(os.path.dirname(current_dir), 'templates')
    
    app = Flask(__name__, template_folder=template_dir)

    # Database Configuration
    uri = os.getenv("DATABASE_URL")
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = uri
    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "789456123321654987")
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    # Register Blueprint with relative import
    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    # AUTO-CREATE TABLES ON STARTUP
    with app.app_context():
        from . import models
        try:
            db.create_all()
            print("Postgres Sync: Tables Created/Verified")
        except Exception as e:
            print(f"Postgres Error: {e}")

    return app
