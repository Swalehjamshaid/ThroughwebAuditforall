from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_required, current_user
from .models import db, Organization

core = Blueprint('core', __name__)

@core.route('/settings/update', methods=['POST'])
@login_required
def update_schedule():
    # User-defined scheduling as per demand
    org = current_user.org
    org.report_frequency = request.form.get('frequency')
    org.report_time = request.form.get('report_time')
    org.timezone = request.form.get('timezone')
    db.session.commit()
    return redirect(url_for('core.dashboard'))
