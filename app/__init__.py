import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from flask_mail import Mail

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
mail = Mail()

def create_app():
    app = Flask(__name__)

    # 1. Database & Security Config
    uri = os.getenv("DATABASE_URL")
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = uri or "sqlite:///local.db"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "your-secure-key-here")
    
    # Mail Config (Referenced from Railway Variables)
    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')

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
            # Verify hashed password
            if user and bcrypt.check_password_hash(user.password_hash, request.form.get('password')):
                login_user(user)
                return redirect(url_for('dashboard'))
            flash('Invalid email or password.')
        return render_template('login.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            from .models import User, Organization
            # Hash the password before storing
            hashed_pwd = bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8')
            
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
        flash('Reporting preferences updated!')
        return redirect(url_for('dashboard'))

    @app.route('/logout')
    def logout():
        logout_user()
        return redirect(url_for('login'))

    with app.app_context():
        db.create_all()

    return app
