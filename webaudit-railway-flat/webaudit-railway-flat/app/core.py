
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from .models import db, Website, Audit
from .tasks import run_lighthouse_audit

core = Blueprint("core", __name__)

# --- Healthcheck endpoint ---
@core.route("/health")
def health():
    return "OK", 200

@core.route("/")
def index():
    # A simple homepage; you can swap back to templates later
    return "WebAudit is running", 200

@core.route("/dashboard")
@login_required
def dashboard():
    websites = Website.query.filter_by(user_id=current_user.id).all()
    latest = []
    for w in websites:
        a = Audit.query.filter_by(website_id=w.id).order_by(Audit.id.desc()).first()
        if a:
            latest.append({
                "url": w.url,
                "overall": a.score_overall,
                "perf": a.score_perf,
                "access": a.score_accessibility,
                "seo": a.score_seo,
                "bp": a.score_best_practices
            })
    return render_template("dashboard.html", latest=latest, websites=websites)

@core.post("/api/audit")
@login_required
def start_audit():
    url = request.json.get("url")
    w = Website.query.filter_by(user_id=current_user.id, url=url).first()
    if not w:
        w = Website(url=url, owner=current_user)
        db.session.add(w)
        db.session.commit()
    run_lighthouse_audit.delay(w.id, w.url)
    return jsonify({"status": "queued"})
