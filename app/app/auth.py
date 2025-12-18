from flask import Blueprint, request, redirect, url_for, render_template, flash
from . import db, mail, bcrypt
from .models import User, Organization
from flask_mail import Message
from flask_login import login_user, current_user, logout_user, login_required

auth = Blueprint('auth', __name__)

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            org_name = request.form.get('org_name')
            email = request.form.get('email')
            username = request.form.get('username')
            password = request.form.get('password')

            # Create Organization
            org = Organization(name=org_name)
            db.session.add(org)
            db.session.flush()  # Get org.id

            # Create User
            hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
            user = User(
                email=email,
                username=username,
                password_hash=hashed_pw,
                organization_id=org.id
            )
            db.session.add(user)
            db.session.commit()

            flash("Registration successful! Check your email to verify.", "success")
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash(f"Registration failed: {str(e)}", "danger")

    return render_template('register.html')

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Add your login logic here when ready
        flash("Login form submitted (implement validation later)", "info")
    return render_template('login.html')

@auth.route('/verify/<user_id>')
def verify(user_id):
    user = User.query.get(user_id)
    if user:
        user.is_confirmed = True
        db.session.commit()
        flash("Email verified successfully!", "success")
    else:
        flash("Invalid verification link.", "danger")
    return redirect(url_for('auth.login'))
