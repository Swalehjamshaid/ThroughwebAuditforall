import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from flask_mail import Mail

# Initialize Extensions
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
mail = Mail()

def create_app():
    app = Flask(__name__)

    # --- DATABASE CONFIGURATION ---
    # Railway often provides 'postgres://', but SQLAlchemy 2.0 requires 'postgresql://'
    # We fix this automatically here.
    database_url = os.getenv("DATABASE_URL")
    
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    # Using your linked Railway variable or a fallback for local testing
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "789456123321654987")

    # --- MAIL CONFIGURATION ---
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
    app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")

    # Initialize App with Extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    
    login_manager.login_view = 'login'

    @login_manager.user_loader
    def load_user(user_id):
        from .models import User
        return User.query.get(user_id)

    # --- ROUTES ---

    @app.route('/')
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            from .models import User
            user = User.query.filter_by(email=request.form.get('email')).first()
            if user and bcrypt.check_password_hash(user.password_hash, request.form.get('password')):
                login_user(user)
                return redirect(url_for('dashboard'))
            flash('Invalid email or password.')
        return render_template('login.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            from .models import User, Organization
            try:
                # Hash password securely
                hashed_pwd = bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8')
                
                # Create Organization
                new_org = Organization(name=request.form.get('org_name'))
                db.session.add(new_org)
                db.session.flush() # Generate Org ID

                # Create User
                new_user = User(
                    username=request.form.get('username'),
                    email=request.form.get('email'),
                    password_hash=hashed_pwd,
                    organization_id=new_org.id
                )
                db.session.add(new_user)
                db.session.commit()
                flash('Account created! Please login.')
                return redirect(url_for('login'))
            except Exception as e:
                db.session.rollback()
                flash(f'Registration Error: {str(e)}')
                return redirect(url_for('register'))
        return render_template('register.html')

    @app.route('/dashboard')
    @login_required
    def dashboard():
        from .models import AuditRun
        audit = AuditRun.query.filter_by(organization_id=current_user.organization_id).order_by(AuditRun.created_at.desc()).first()
        return render_template('dashboard.html', audit=audit)

    @app.route('/settings/update', methods=['POST'])
    @login_required
    def update_settings():
        from .models import Organization
        org = Organization.query.get(current_user.organization_id)
        org.report_frequency = request.form.get('frequency')
        org.report_time = request.form.get('report_time')
        org.timezone = request.form.get('timezone')
        db.session.commit()
        flash('Preferences updated!')
        return redirect(url_for('dashboard'))

    @app.route('/logout')
    def logout():
        logout_user()
        return redirect(url_for('login'))

    # --- AUTOMATIC DATABASE SYNC ---
    with app.app_context():
        try:
            from . import models
            db.create_all()
            print("Postgres: Connection and table sync successful.")
        except Exception as e:
            print(f"Postgres: Sync failed. Error: {e}")

    return app
