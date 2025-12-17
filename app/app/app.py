from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_bcrypt import Bcrypt
from .config import Config

db = SQLAlchemy()
mail = Mail()
bcrypt = Bcrypt()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__, template_folder='../templates')
    app.config.from_object(Config)
    db.init_app(app)
    mail.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)

    with app.app_context():
        from .auth import auth
        from .core import core
        app.register_blueprint(auth)
        app.register_blueprint(core)
        db.create_all() # Automatically builds Railway Database tables
    return app

@login_manager.user_loader
def load_user(user_id):
    from .models import User
    return User.query.get(user_id)
