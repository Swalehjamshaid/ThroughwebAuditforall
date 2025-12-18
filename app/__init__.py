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
    # Railway provides 'postgres://', but SQLAlchemy 2.0 requires 'postgresql://'
    database_url = os.getenv("DATABASE_URL")
    
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "789456123321654987")

    # Initialize extensions with the app
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(user_id)

    # --- REGISTRATION LOGIC ---
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            from app.models import User, Organization
            try:
                # Use bcrypt to hash the password securely
                hashed_pwd = bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8')
                
                # Create Organization and User
                new_org = Organization(name=request.form.get('org_name'))
                db.session.add(new_org)
                db.session.flush()

                new_user = User(
                    username=request.form.get('username'),
                    email=request.form.get('email'),
                    password_hash=hashed_pwd,
                    organization_id=new_org.id
                )
                db.session.add(new_user)
                db.session.commit()
                flash('Registration successful! Please login.')
                return redirect(url_for('login'))
            except Exception as e:
                db.session.rollback()
                flash(f"Error: {str(e)}")
        return render_template('register.html')

    # --- OTHER ROUTES ---
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            from app.models import User
            user = User.query.filter_by(email=request.form.get('email')).first()
            if user and bcrypt.check_password_hash(user.password_hash, request.form.get('password')):
                login_user(user)
                return redirect(url_for('dashboard'))
            flash('Invalid email or password.')
        return render_template('login.html')

    @app.route('/dashboard')
    @login_required
    def dashboard():
        from app.models import AuditRun
        audit = AuditRun.query.filter_by(organization_id=current_user.organization_id).order_by(AuditRun.created_at.desc()).first()
        return render_template('dashboard.html', audit=audit)

    # --- THE "FILL TABLE" TRIGGER ---
    with app.app_context():
        try:
            from app import models
            db.create_all()  # This creates the tables in your Railway Postgres service
            print("Postgres Sync: SUCCESS")
        except Exception as e:
            print(f"Postgres Sync: FAILED - {e}")

    return app
