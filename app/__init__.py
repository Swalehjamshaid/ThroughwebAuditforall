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
    # Pointing to the template folder inside the nested structure
    template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
    app = Flask(__name__, template_folder=template_dir)

    # --- DATABASE INTEGRATION ---
    database_url = os.getenv("DATABASE_URL")
    # Fix for SQLAlchemy 2.0
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "your-secret-key-123")

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    @login_manager.user_loader
    def load_user(user_id):
        import models # Direct import due to sys.path fix in run.py
        return models.User.query.get(user_id)

    # --- REGISTRATION FUNCTION ---
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            import models
            try:
                hashed_pwd = bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8')
                new_org = models.Organization(name=request.form.get('org_name'))
                db.session.add(new_org)
                db.session.flush()

                new_user = models.User(
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
                flash(f"Database Error: {str(e)}")
        return render_template('register.html')

    # --- LOGIN FUNCTION ---
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            import models
            user = models.User.query.filter_by(email=request.form.get('email')).first()
            if user and bcrypt.check_password_hash(user.password_hash, request.form.get('password')):
                login_user(user)
                return redirect(url_for('dashboard'))
            flash('Invalid email or password.')
        return render_template('login.html')

    @app.route('/dashboard')
    @login_required
    def dashboard():
        import models
        audit = models.AuditRun.query.filter_by(organization_id=current_user.organization_id).order_by(models.AuditRun.created_at.desc()).first()
        return render_template('dashboard.html', audit=audit)

    # --- AUTO-CREATE TABLES ---
    with app.app_context():
        try:
            import models
            db.create_all()
            print("Postgres: Tables Synchronized Successfully")
        except Exception as e:
            print(f"Postgres Error: {e}")

    return app
