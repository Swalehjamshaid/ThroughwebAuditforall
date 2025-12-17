import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'audit-secret-999')
    # Auto-converts Railway DB URL for SQLAlchemy compatibility
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', '').replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REDIS_URL = os.environ.get('REDIS_URL')
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
