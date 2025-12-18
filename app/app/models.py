import uuid
from datetime import datetime
from flask_login import UserMixin
from . import db  # Import from same package (app.app)

class Organization(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), nullable=False)
    users = db.relationship('User', backref='org', lazy=True)

class User(db.Model, UserMixin):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(100), unique=True, nullable=False)
    username = db.Column(db.String(80))
    password_hash = db.Column(db.String(200), nullable=False)
    is_confirmed = db.Column(db.Boolean, default=False)
    organization_id = db.Column(db.String(36), db.ForeignKey('organization.id'))
