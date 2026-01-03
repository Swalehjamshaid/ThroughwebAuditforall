
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email_confirmed = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(20), default='user')  # 'user' or 'admin'
    free_audits_used = db.Column(db.Integer, default=0)
    subscription_active = db.Column(db.Boolean, default=False)
    schedule_enabled = db.Column(db.Boolean, default=False)
    schedule_time = db.Column(db.String(5), nullable=True)  # 'HH:MM'
    schedule_timezone = db.Column(db.String(64), nullable=True)  # e.g. 'Asia/Karachi'
    next_run_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Website(db.Model):
    __tablename__ = 'websites'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    url = db.Column(db.String(2048), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Audit(db.Model):
    __tablename__ = 'audits'
    id = db.Column(db.Integer, primary_key=True)
    website_id = db.Column(db.Integer, db.ForeignKey('websites.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    health_score = db.Column(db.Float, default=0.0)
    errors = db.Column(db.Integer, default=0)
    warnings = db.Column(db.Integer, default=0)
    notices = db.Column(db.Integer, default=0)
    pdf_path = db.Column(db.String(1024), nullable=True)

class AuditMetric(db.Model):
    __tablename__ = 'audit_metrics'
    id = db.Column(db.Integer, primary_key=True)
    audit_id = db.Column(db.Integer, db.ForeignKey('audits.id'), nullable=False)
    key = db.Column(db.String(128), nullable=False)
    value = db.Column(db.String(2048), nullable=True)
    level = db.Column(db.String(20), default='info')  # error/warning/info
