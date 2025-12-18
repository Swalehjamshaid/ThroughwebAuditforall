import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from flask_mail import Mail

# Initialize extensions globally
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
mail = Mail()

def create_app():
    # LINK TEMPLATES: Points back to ThroughwebAuditforall/app/templates
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(os.path.dirname(current_dir), 'templates')
    
    app = Flask(__name__, template_folder=template_dir)

    # DATABASE LINKING
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
        from .models import User
        return User.query.get(user_id)

    # REGISTER BLUEPRINTS using relative imports
    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    # MAIN ROUTES
    @app.route('/dashboard')
    @login_required
    def dashboard():
        from .models import AuditRun
        audit = AuditRun.query.filter_by(organization_id=current_user.organization_id).order_by(AuditRun.created_at.desc()).first()
        return render_template('dashboard.html', audit=audit)

    # TRIGGER TABLE CREATION (Fills the Postgres DB on Railway)
    with app.app_context():
        from . import models
        try:
            db.create_all()
            print("Postgres Sync: Success - Tables Created/Verified")
        except Exception as e:
            print(f"Postgres Sync: Failed - {e}")

    return app
