
# app/app/core.py
from flask import Blueprint

core = Blueprint("core", __name__)

@core.route("/health")
def health():
    return "OK", 200

@core.route("/")
def index():
    return "WebAudit is running", 200
