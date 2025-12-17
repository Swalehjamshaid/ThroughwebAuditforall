from flask import Blueprint, request, redirect, url_for, render_template
from .app import db, mail, bcrypt
from .models import User, Organization
from flask_mail import Message

auth = Blueprint('auth', __name__)

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Create Org first (Tenant)
        org = Organization(name=request.form.get('org_name'))
        db.session.add(org)
        db.session.flush()
        
        hashed_pw = bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8')
        user = User(email=request.form.get('email'), username=request.form.get('username'),
                    password_hash=hashed_pw, organization_id=org.id)
        db.session.add(user)
        db.session.commit()

        # Requirement: Email Confirmation
        msg = Message("Verify Your ThroughwebAudit Account", recipients=[user.email])
        msg.body = f"Verify here: {url_for('auth.verify', user_id=user.id, _external=True)}"
        mail.send(msg)
        return "Check your email to verify and logon!"
    return render_template('register.html')

@auth.route('/verify/<user_id>')
def verify(user_id):
    user = User.query.get(user_id)
    if user:
        user.is_confirmed = True
        db.session.commit()
    return redirect(url_for('auth.login'))
