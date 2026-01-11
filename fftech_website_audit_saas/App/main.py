from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import os

from modules.data_store import get_connection, init_db
from modules.audit import get_audits, get_audit_by_id, create_audit, add_audit_item, get_items_for_audit
from modules.registration import register_user, get_users
from modules.grader import compute_metrics
from modules.utils import generate_charts
from modules.report import generate_pdf_report

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'replace-this-with-a-strong-secret'

@app.before_first_request
def setup():
    conn = get_connection()
    init_db(conn)
    conn.close()

@app.route('/')
def dashboard():
    conn = get_connection()
    audits = get_audits(conn)
    users = get_users(conn)
    summary = []
    for a in audits[:5]:
        metrics = compute_metrics(conn, a['id'])
        summary.append({'audit': a, 'metrics': metrics})
    conn.close()
    return render_template('dashboard.html', audits=audits, users=users, summary=summary)

@app.route('/audits')
def audits_list():
    conn = get_connection()
    audits = get_audits(conn)
    conn.close()
    return render_template('audit_list.html', audits=audits)

@app.route('/audit/new', methods=['GET', 'POST'])
def audit_new():
    if request.method == 'POST':
        title = request.form.get('title')
        category = request.form.get('category')
        creator = request.form.get('creator')
        if not title:
            flash('Title is required', 'error')
            return redirect(url_for('audit_new'))
        conn = get_connection()
        audit_id = create_audit(conn, title=title, category=category, created_by=creator)
        conn.close()
        flash('Audit created', 'success')
        return redirect(url_for('audit_detail', audit_id=audit_id))
    return render_template('audit_form.html')

@app.route('/audit/<int:audit_id>', methods=['GET', 'POST'])
def audit_detail(audit_id):
    conn = get_connection()
    audit = get_audit_by_id(conn, audit_id)
    items = get_items_for_audit(conn, audit_id)
    if not audit:
        conn.close()
        flash('Audit not found', 'error')
        return redirect(url_for('audits_list'))

    if request.method == 'POST':
        item = request.form.get('item')
        weight = float(request.form.get('weight') or 1)
        score = float(request.form.get('score') or 0)
        status = request.form.get('status') or 'pending'
        add_audit_item(conn, audit_id, item, weight, score, status)
        flash('Item added', 'success')
        conn.close()
        return redirect(url_for('audit_detail', audit_id=audit_id))

    conn.close()
    return render_template('audit_detail.html', audit=audit, items=items)

@app.route('/results/<int:audit_id>')
def audit_results(audit_id):
    conn = get_connection()
    audit = get_audit_by_id(conn, audit_id)
    if not audit:
        conn.close()
        flash('Audit not found', 'error')
        return redirect(url_for('audits_list'))
    metrics = compute_metrics(conn, audit_id)
    chart_paths = generate_charts(conn, audit_id, output_dir=os.path.join(app.static_folder, 'img'))
    conn.close()
    return render_template('results.html', audit=audit, metrics=metrics, charts=chart_paths)

@app.route('/reports/<int:audit_id>')
def audit_report(audit_id):
    conn = get_connection()
    audit = get_audit_by_id(conn, audit_id)
    if not audit:
        conn.close()
        flash('Audit not found', 'error')
        return redirect(url_for('audits_list'))
    chart_paths = generate_charts(conn, audit_id, output_dir=os.path.join(app.static_folder, 'img'))
    pdf_path = generate_pdf_report(conn, audit_id, chart_paths)
    conn.close()
    return send_file(pdf_path, as_attachment=True)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        role = request.form.get('role')
        if not name or not email:
            flash('Name and email are required', 'error')
            return redirect(url_for('register'))
        conn = get_connection()
        register_user(conn, name=name, email=email, role=role)
        conn.close()
        flash('User registered', 'success')
        return redirect(url_for('users_list'))
    return render_template('registration.html')

@app.route('/users')
def users_list():
    conn = get_connection()
    users = get_users(conn)
    conn.close()
    return render_template('users.html', users=users)

if __name__ == '__main__':
    app.run(debug=True)
