import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    application = Flask(__name__)
    
    # DB Logic
    uri = os.getenv("DATABASE_URL")
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    
    application.config['SQLALCHEMY_DATABASE_URI'] = uri or "sqlite:///local.db"
    application.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(application)
    
    @application.route('/')
    def index():
        return "Throughweb Audit System is Online"

    with application.app_context():
        from . import models
        db.create_all()

    return application
