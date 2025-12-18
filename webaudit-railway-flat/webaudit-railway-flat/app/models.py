
from datetime import datetime
from flask_login import UserMixin
from . import db

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default="user")
    websites = db.relationship('Website', backref='owner', lazy=True)

class Website(db.Model):
    id = db.Column(db.Integer, primary key=True)
    url = db.Column(db.String(500), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    audits = db.relationship('Audit', backref='website', lazy=True)

class Audit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime)
    status = db.Column(db.String(32), default="queued")
    score_overall = db.Column(db.Float)
    score_perf = db.Column(db.Float)
    score_accessibility = db.Column(db.Float)
    score_best_practices = db.Column(db.Float)
    score_seo = db.Column(db.Float)
    score_pwa = db.Column(db.Float)
    lighthouse_json = db.Column(db.JSON)
    metrics_json = db.Column(db.JSON)
    website_id = db.Column(db.Integer, db.ForeignKey('website.id'))

class EmailSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    website_id = db.Column(db.Integer, db.ForeignKey('website.id'))
    frequency = db.Column(db.String(32), default="weekly")
    cron = db.Column(db.String(64))
    active = db.Column(db.Boolean, default=True)
