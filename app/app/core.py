
# app/app/core.py
from flask import Blueprint, render_template
from flask_login import login_required, current_user

core = Blueprint("core", __name__)

@core.route("/")
def index():
    return render_template("index.html")

@core.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user)
``
