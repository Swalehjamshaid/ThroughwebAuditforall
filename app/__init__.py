import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt

# Initialize extensions
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)

    # --- DATABASE LINKING ---
    # This pulls the DATABASE_URL you just set in the Railway variables
    uri = os.getenv("DATABASE_URL")
    
    # Safety check: SQLAlchemy requires 'postgresql://' (which your vars have)
    # But we keep this fix just in case Railway's internal string changes
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "789456123321654987")

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    @login_manager.user_loader
    def load_user(user_id):
        # We use absolute imports to fix the ModuleNotFoundError
        from app.models import User
        return User.query.get(user_id)

    # --- REGISTRATION ROUTE ---
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            from app.models import User, Organization
            try:
                hashed_pwd = bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8')
                
                # Create the Organization
                new_org = Organization(name=request.form.get('org_name'))
                db.session.add(new_org)
                db.session.flush()

                # Create the User
                new_user = User(
                    username=request.form.get('username'),
                    email=request.form.get('email'),
                    password_hash=hashed_pwd,
                    organization_id=new_org.id
                )
                db.session.add(new_user)
                db.session.commit()
                flash('Registration successful!')
                return redirect(url_for('login'))
            except Exception as e:
                db.session.rollback()
                print(f"DEBUG: Registration failed: {e}")
                flash("Error connecting to database.")
        return render_template('register.html')

    # --- DATABASE SYNC ---
    with app.app_context():
        try:
            from app import models
            db.create_all()
            print("Postgres: Database tables synchronized successfully.")
        except Exception as e:
            print(f"Postgres Error: Could not connect or create tables: {e}")

    return app
