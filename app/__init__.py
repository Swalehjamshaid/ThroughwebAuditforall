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
    # Template folder: go up two levels from app/app/__init__.py → reaches /app/templates
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.abspath(os.path.join(current_dir, '..', '..', 'templates'))

    app = Flask(__name__, template_folder=template_dir)

    # Database URL fix for Railway/Postgres
    uri = os.getenv("DATABASE_URL")
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = uri
    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "super-secret-key-change-in-prod")
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Mail configuration (optional – only needed if sending emails)
    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        from .models import User
        return User.query.get(user_id)

    # Register blueprint
    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    # Create tables on startup
    with app.app_context():
        from . import models
        db.create_all()
        print("--- SYSTEM STATUS: DATABASE SYNC SUCCESSFUL ---")

    return app
