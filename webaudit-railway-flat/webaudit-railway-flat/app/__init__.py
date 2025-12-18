
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

    uri = os.getenv("DATABASE_URL")
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = uri
    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "supersecret-dev-key")
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Email
    app.config['MAIL_SERVER']   = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    app.config['MAIL_PORT']     = int(os.getenv("MAIL_PORT", "587"))
    app.config['MAIL_USE_TLS']  = True
    app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
    app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv("MAIL_DEFAULT_SENDER", os.getenv("MAIL_USERNAME"))

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        from .models import User
        return User.query.get(user_id)

    from .auth import auth as auth_blueprint
    from .core import core as core_blueprint
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(core_blueprint)

    # Optional APScheduler
    if os.getenv("USE_APSCHEDULER", "false").lower() == "true":
        from .scheduler import init_scheduler
        init_scheduler(app)

    with app.app_context():
        from . import models
        db.create_all()

    return app
