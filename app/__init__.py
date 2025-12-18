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
    # Fix: Tell Flask where templates are (since this file is nested)
    template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
    app = Flask(__name__, template_folder=template_dir)

    # --- DATABASE CONFIG ---
    database_url = os.getenv("DATABASE_URL")
    
    # Railway provides 'postgres://', but SQLAlchemy 2.0 requires 'postgresql://'
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "your-secure-key-123")

    # Initialize extensions with the app
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    @login_manager.user_loader
    def load_user(user_id):
        import models  # Absolute import from the same folder
        return models.User.query.get(user_id)

    # --- ROUTES ---

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
                return redirect(url_for('login'))
            except Exception as e:
                db.session.rollback()
                flash(f"Error: {str(e)}")
        return render_template('register.html')

    # --- AUTOMATIC TABLE FILL ---
    with app.app_context():
        try:
            import models
            db.create_all()  # This builds the tables in your Railway database
            print("Postgres: Tables Created/Verified Successfully")
        except Exception as e:
            print(f"Postgres Error: {e}")

    return app
