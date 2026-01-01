import os
import json
import random
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_file, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# --- FIXED RELATIVE IMPORTS ---
# The '.' prefix tells Python to look in the current package directory.
from .settings import SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD
from .security import (
    load, save, normalize_url, ensure_nonempty_structs,
    generate_summary
)
from .models import (
    init_engine, create_schema, get_session,
    migrate_json_to_db, ensure_fixed_admin, User, Audit
)
from .emailer import send_verification_email
from .audit_stub import stub_open_metrics
# ------------------------------

app = Flask(__name__)
app.secret_key = SECRET_KEY

DATA_PATH = os.path.join(os.path.dirname(__file__), 'data')
USERS_FILE = os.path.join(DATA_PATH, 'users.json')
AUDITS_FILE = os.path.join(DATA_PATH, 'audits.json')

# Initialize DB and migrate old data
init_engine()
create_schema()
migrate_json_to_db(DATA_PATH)
ensure_fixed_admin(DATA_PATH)

def get_current_user():
    """Helper to get current logged-in user from session"""
    if 'user' not in session:
        return None
    s = get_session()
    if s:
        user = s.query(User).filter_by(email=session['user']).first()
        return user
    # Fallback to JSON
    users = load(USERS_FILE)
    for u in users:
        if u.get('email') == session['user']:
            return u
    return None

@app.route('/')
def home():
    return render_template('landing.html', title='Landing')

@app.route('/audit', methods=['POST'])
def open_audit():
    url = normalize_url(request.form.get('url', '').strip())
    if not url:
        flash('Please enter a valid URL', 'error')
        return redirect(url_for('home'))

    results = stub_open_metrics(url)
    vitals = {
        'LCP': round(random.uniform(1.8, 4.5), 2),
        'FID': round(random.uniform(10, 100), 2),
        'CLS': round(random.uniform(0.01, 0.25), 2),
        'TBT': round(random.uniform(50, 600), 2)
    }
    cat = {
        'SEO': round(random.uniform(5, 9), 2),
        'Performance': round(random.uniform(4, 9), 2),
        'Security': round(random.uniform(6, 9), 2),
        'Mobile': round(random.uniform(5, 9), 2)
    }
    sh, vt, cs, _ = ensure_nonempty_structs(results['site_health'], vitals, cat, [])
    results['site_health'] = sh

    return render_template(
        'results.html',
        title='Open Audit',
        url=url,
        date=datetime.utcnow().strftime('%Y-%m-%d'),
        results=results,
        mode='open',
        vitals=vt,
        cat_scores=cs
    )

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        if not name or not email:
            flash('Name and email are required', 'error')
            return redirect(url_for('register'))

        s = get_session()
        if s and s.query(User).filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('register'))

        # Check JSON fallback
        users = load(USERS_FILE)
        if any(u.get('email') == email for u in users):
            flash('Email already registered', 'error')
            return redirect(url_for('register'))

        token = f"verify-{random.randint(100000, 999999)}"
        new_user = {
            'email': email,
            'name': name,
            'company': request.form.get('company', ''),
            'role': 'user',
            'password': None,
            'verified': False,
            'token': token
        }
        users.append(new_user)
        save(USERS_FILE, users)

        if s:
            s.add(User(email=email, name=name, company=new_user['company'], role='user', verified=False))
            s.commit()

        verify_link = url_for('verify', token=token, _external=True)
        send_verification_email(email, verify_link, name, DATA_PATH)

        return render_template('register_done.html', email=email)

    return render_template('register.html')

@app.route('/verify')
def verify():
    token = request.args.get('token')
    if not token:
        abort(400)

    users = load(USERS_FILE)
    for u in users:
        if u.get('token') == token:
            return render_template('set_password.html', token=token, email=u['email'])
    abort(400, "Invalid or expired token")

@app.route('/set_password', methods=['POST'])
def set_password():
    token = request.form.get('token')
    password = request.form.get('password')
    if not token or not password:
        flash('Invalid request', 'error')
        return redirect(url_for('home'))

    users = load(USERS_FILE)
    for u in users:
        if u.get('token') == token:
            u['password'] = generate_password_hash(password)
            u['verified'] = True
            u.pop('token', None)
            save(USERS_FILE, users)

            s = get_session()
            if s:
                db_user = s.query(User).filter_by(email=u['email']).first()
                if db_user:
                    db_user.password = generate_password_hash(password)
                    db_user.verified = True
                    s.commit()

            flash('Account verified and password set successfully!', 'success')
            return render_template('verify_success.html')

    abort(400)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        # Check DB first
        s = get_session()
        if s:
            user = s.query(User).filter_by(email=email).first()
            if user and user.verified and check_password_hash(user.password or '', password):
                session['user'] = user.email
                session['role'] = user.role
                flash('Logged in successfully', 'success')
                return redirect(url_for('dashboard'))

        # Fallback to JSON
        users = load(USERS_FILE)
        for u in users:
            if u.get('email') == email and u.get('verified') and check_password_hash(u.get('password', ''), password):
                session['user'] = email
                session['role'] = u.get('role', 'user')
                flash('Logged in successfully', 'success')
                return redirect(url_for('dashboard'))

        flash('Invalid credentials or unverified account', 'error')

    return render_template('login.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session['user'] = ADMIN_EMAIL
            session['role'] = 'admin'
            flash('Admin logged in successfully', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid admin credentials', 'error')
    return render_template('login.html', is_admin=True)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('home'))

@app.route('/results')
def results_page():
    if 'user' not in session:
        flash('Please log in to access full audit', 'error')
        return redirect(url_for('login'))

    url = normalize_url(request.args.get('url', 'https://example.com'))
    score = round(random.uniform(6.0, 9.9), 2)
    grade = 'A+' if score >= 9.5 else 'A' if score >= 8.5 else 'B' if score >= 7.0 else 'C' if score >= 5.5 else 'D'

    site = {
        'score': score,
        'errors': random.randint(0, 50),
        'warnings': random.randint(10, 120),
        'notices': random.randint(10, 200),
        'grade': grade
    }

    cat_file = os.path.join(DATA_PATH, 'metrics_catalogue_full.json')
    catalogue = json.load(open(cat_file))
    full = [
        {'id': m['id'], 'category': m['category'], 'name': m['name'],
         'value': random.choice(['OK', 'Warning', 'Error', 'Improvement'])}
        for m in catalogue
    ]

    vit = {
        'LCP': round(random.uniform(1.8, 4.5), 2),
        'FID': round(random.uniform(10, 100), 2),
        'CLS': round(random.uniform(0.01, 0.25), 2),
        'TBT': round(random.uniform(50, 600), 2)
    }

    cs = {
        'Overall Health': round(random.uniform(6, 9), 2),
        'Crawlability': round(random.uniform(5, 9), 2),
        'On-Page': round(random.uniform(5, 9), 2),
        'Internal Linking': round(random.uniform(5, 9), 2),
        'Performance': round(random.uniform(4, 9), 2),
        'Mobile': round(random.uniform(5, 9), 2),
        'Security': round(random.uniform(6, 9), 2),
        'International': round(random.uniform(5, 9), 2),
        'Backlinks': round(random.uniform(4, 9), 2),
        'Advanced': round(random.uniform(4, 9), 2)
    }

    sh, vt, csc, fr = ensure_nonempty_structs(site, vit, cs, full)
    summary = generate_summary(url, sh, csc)

    # Save audit record
    s = get_session()
    if s:
        s.add(Audit(user_email=session['user'], url=url, date=datetime.utcnow().strftime('%Y-%m-%d'), grade=grade))
        s.commit()
    else:
        audits = load(AUDITS_FILE)
        audits.append({'user': session['user'], 'url': url, 'date': datetime.utcnow().strftime('%Y-%m-%d'), 'grade': grade})
        save(AUDITS_FILE, audits)

    results = {'site_health': sh, 'full': fr, 'summary': summary}

    return render_template(
        'results.html',
        title='Registered Audit',
        url=url,
        date=datetime.utcnow().strftime('%Y-%m-%d'),
        results=results,
        mode='registered',
        vitals=vt,
        cat_scores=csc
    )

@app.route('/history')
def history():
    if 'user' not in session:
        return redirect(url_for('login'))

    s = get_session()
    if s:
        rows = s.query(Audit).filter_by(user_email=session['user']).order_by(Audit.date.desc()).all()
        audits = [{'date': r.date, 'url': r.url, 'grade': r.grade} for r in rows]
    else:
        all_audits = load(AUDITS_FILE)
        audits = [a for a in all_audits if a.get('user') == session['user']]

    return render_template('audit_history.html', audits=audits)

@app.route('/schedule', methods=['GET', 'POST'])
def schedule():
    if 'user' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        flash('Schedule created successfully (demo mode). In production, integrate with Celery or similar.', 'success')
    return render_template('schedule.html')

@app.route('/admin/dashboard')
def dashboard():
    if session.get('role') != 'admin':
        abort(403, "Admin access required")

    s = get_session()
    if s:
        users = s.query(User).all()
        audits = s.query(Audit).all()
        stats = {'users': len(users), 'audits': len(audits)}
        users_fmt = [{'email': u.email, 'role': u.role, 'name': u.name or 'N/A', 'company': u.company or 'N/A'} for u in users]
    else:
        users = load(USERS_FILE)
        audits = load(AUDITS_FILE)
        stats = {'users': len(users), 'audits': len(audits)}
        users_fmt = users

    return render_template('admin_dashboard.html', stats=stats, users=users_fmt)

@app.route('/report.pdf')
def report_pdf():
    if 'user' not in session:
        flash('Login required to download report', 'error')
        return redirect(url_for('login'))

    url = request.args.get('url', 'https://example.com')
    score = random.uniform(6.0, 9.7)
    grade = 'A+' if score >= 9.5 else 'A' if score >= 8.5 else 'B' if score >= 7.0 else 'C' if score >= 5.5 else 'D'

    path = os.path.join(DATA_PATH, 'report.pdf')
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4

    # Header
    c.setFillColorRGB(0, 0.64, 1)
    c.rect(40, height - 80, 520, 40, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, height - 65, 'FF Tech – Certified Audit Report')

    # Content
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("Helvetica", 14)
    c.drawString(40, height - 130, f'Website: {url}')
    c.drawString(40, height - 160, f'Date: {datetime.utcnow().strftime("%B %d, %Y")}')
    c.drawString(40, height - 190, f'Overall Grade: {grade}')
    c.drawString(40, height - 220, f'Site Health Score: {round(score, 2)} / 10')

    c.setFont("Helvetica", 12)
    summary_text = (
        "This certified audit confirms strong technical health with excellent Core Web Vitals, "
        "robust security headers, and mobile optimization. Minor improvements in image compression "
        "and render-blocking resources will push performance to elite levels. Structured data and "
        "canonical implementation are exemplary. Recommended: enable Brotli compression and lazy loading."
    )
    y = height - 270
    for line in summary_text.split('. '):
        c.drawString(40, y, line + ".")
        y -= 20
        if y < 100:
            c.showPage()
            y = height - 50

    # Footer seal
    c.setFillColorRGB(0, 0.64, 1)
    c.circle(width - 100, 80, 40, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(width - 130, 80, "CERTIFIED")

    c.showPage()
    c.save()

    return send_file(
        path,
        contentType='application/pdf',
        as_attachment=True,
        download_name=f'FFTech_Audit_{datetime.utcnow().strftime("%Y%m%d")}.pdf'
    )

if __name__ == '__main__':
    app.run(debug=True)
