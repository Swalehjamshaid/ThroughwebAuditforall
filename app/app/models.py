import uuid
from datetime import datetime
from flask_login import UserMixin
from . import db

class Organization(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), nullable=False)
    report_frequency = db.Column(db.String(20), default='weekly')
    report_time = db.Column(db.String(5), default='09:00') 
    timezone = db.Column(db.String(50), default='UTC')
    users = db.relationship('User', backref='org', lazy=True)

class User(db.Model, UserMixin):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(100), unique=True, nullable=False)
    username = db.Column(db.String(80))
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='customer') 
    organization_id = db.Column(db.String(36), db.ForeignKey('organization.id'))

class AuditRun(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    website_url = db.Column(db.String(255))
    overall_score = db.Column(db.Integer, default=0)
    metrics_json = db.Column(db.JSON)
    organization_id = db.Column(db.String(36), db.ForeignKey('organization.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
