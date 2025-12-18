
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

    # --- Database URL (Railway will provide DATABASE_URL) ---
    uri = os.getenv("DATABASE_URL")
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    # Graceful fallback for healthcheck/dev if DATABASE_URL missing
    if not uri:
        uri = "sqlite:///app.db"

    app.config["SQLALCHEMY_DATABASE_URI"] = uri
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "supersecret-dev-key")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # --- Mail (optional). If this causes startup issues, comment mail.init_app(app) below ---
    app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
    app.config["MAIL_USE_TLS"] = True
    app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
    app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER", os.getenv("MAIL_USERNAME"))

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        from .app.models import User
        return User.query.get(user_id)

    # --- REGISTER BLUEPRINTS (NOTE nested imports .app.*) ---
    from .app.auth import auth as auth_blueprint
    from .app.core import core as core_blueprint
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(core_blueprint)

    # Create DB tables
    with app.app_context():
        from .app import models
        db.create_all()

    return app
