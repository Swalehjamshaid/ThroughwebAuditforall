import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    # Pointing to templates folder located at ThroughwebAuditforall/app/templates
    template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
    app = Flask(__name__, template_folder=template_dir)

    # ... (rest of your configuration)

    # CRITICAL: Use relative import for blueprints and models
    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    with app.app_context():
        from . import models # Relative import
        db.create_all()
        print("Postgres Sync: Success")

    return app
