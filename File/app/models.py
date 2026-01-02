# app/models.py
from app import db, login
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(64))
    audit_count = db.Column(db.Integer, default=0)
    subscription_active = db.Column(db.Boolean, default=False)
    subscription_id = db.Column(db.String(64))
    subscription_start = db.Column(db.DateTime)
    subscription_end = db.Column(db.DateTime)

    websites = db.relationship('Website', backref='owner', lazy='dynamic')
    audits = db.relationship('Audit', backref='user', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @login.load_user
    def load_user(id):
        return User.query.get(int(id))

class Website(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(256))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    schedule = db.Column(db.String(64))  # e.g., 'daily', 'weekly'

    audits = db.relationship('Audit', backref='website', lazy='dynamic')

class Audit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    website_id = db.Column(db.Integer, db.ForeignKey('website.id'))
    report = db.Column(db.JSON)  # Store metrics as JSON
    grade = db.Column(db.String(2))
    pdf_path = db.Column(db.String(256))
