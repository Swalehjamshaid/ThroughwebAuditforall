from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from .models import db

core = Blueprint('core', __name__)

@core.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@core.route('/settings/update', methods=['POST'])
@login_required
def update_schedule():
    org = current_user.org
    org.report_frequency = request.form.get('frequency')
    org.report_time = request.form.get('report_time')
    org.timezone = request.form.get('timezone')
    db.session.commit()
    flash("Schedule updated!", "success")
    return redirect(url_for('core.dashboard'))
