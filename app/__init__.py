
# app/__init__.py
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_mail import Mail

# Initialize globally
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
mail = Mail()

def create_app():
    # Templates live under top-level app/templates
    template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
    app = Flask(__name__, template_folder=template_dir)

    # Database Configuration (Railway postgres:// -> postgresql:// fix)
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

    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        # models.py is under nested package app/app/models.py
        from .app.models import User
        return User.query.get(user_id)

    # Register Blueprints — NOTE the nested package path ".app.auth" & ".app.core"
    from .app.auth import auth as auth_blueprint
    from .app.core import core as core_blueprint
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(core_blueprint)

    # Sync Database on boot
    with app.app_context():
        # Import models from nested package
        from .app import models
        db.create_all()
        print("--- DATABASE STATUS: CONNECTED & SYNCED ---")

   
