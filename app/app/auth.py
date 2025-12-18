from flask import Blueprint, request, redirect, url_for, render_template, flash
from . import db, mail, bcrypt
from .models import User, Organization
from flask_mail import Message

auth = Blueprint('auth', __name__)

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            # Create Organization
            org = Organization(name=request.form.get('org_name'))
            db.session.add(org)
            db.session.flush()
            
            # Create User
            hashed_pw = bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8')
            user = User(
                email=request.form.get('email'), 
                username=request.form.get('username'),
                password_hash=hashed_pw, 
                organization_id=org.id
            )
            db.session.add(user)
            db.session.commit()

            # Send verification link
            msg = Message("Verify Your Account", recipients=[user.email])
            msg.body = f"Click here to verify: {url_for('auth.verify', user_id=user.id, _external=True)}"
            mail.send(msg)
            
            flash("Success! Check your email to verify.")
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {str(e)}")
            
    return render_template('register.html')

@auth.route('/login')
def login():
    return render_template('login.html')

@auth.route('/verify/<user_id>')
def verify(user_id):
    from .models import User
    user = User.query.get(user_id)
    if user:
        user.is_confirmed = True
        db.session.commit()
    return redirect(url_for('auth.login'))
