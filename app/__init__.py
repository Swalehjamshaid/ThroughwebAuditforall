import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_mail import Mail

# Initialize globally to avoid circular imports
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
mail = Mail()

def create_app():
    # LINK TEMPLATES: Points to /app/templates relative to this file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.abspath(os.path.join(current_dir, '..', 'templates'))
    
    app = Flask(__name__, template_folder=template_dir)

    # DATABASE LINKING
    uri = os.getenv("DATABASE_URL")
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = uri
    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "789456123321654987")
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Init extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        from .models import User
        return User.query.get(user_id)

    # REGISTER BLUEPRINTS
    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    # SYNC DATABASE: This creates the tables in your Railway Dashboard
    with app.app_context():
        from . import models
        db.create_all()
        print("--- SYSTEM STATUS: DATABASE SYNC SUCCESSFUL ---")

    return app
