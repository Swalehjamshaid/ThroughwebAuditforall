
# app/__init__.py
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
    app = Flask(__name__, template_folder="templates", static_folder="static")

    # Fix Railway's legacy scheme automatically
    uri = os.getenv("DATABASE_URL")
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = uri
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "supersecret-dev-key")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Mail (optional). Comment these lines temporarily if startup still fails.
    app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
    app.config["MAIL_USE_TLS"] = True
    app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
    app.config    app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER", os.getenv("MAIL_USERNAME"))

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        from .app.models import User
        return User.query.get(user_id)

    # --- REGISTER BLUEPRINTS ---
    from .app.auth import auth as auth_blueprint
    from .app.core import core as core_blueprint
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(core_blueprint)

    # Create DB tables at startup
    with app.app_context():
        from .app import models
        db.create_all()

