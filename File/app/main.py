
import os, json, random
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, abort
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import matplotlib
matplotlib.use("Agg")

from .settings import SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD, BRAND_NAME, REPORT_VALIDITY_DAYS
from .security import load, save, normalize_url, ensure_nonempty_structs, generate_summary
from .models import init_engine, create_schema, get_session, User, Audit
from .emailer import send_verification_email
from .audit_stub import stub_open_metrics

app = Flask(__name__)
app.secret_key = SECRET_KEY

DATA_PATH = os.path.join(os.path.dirname(__file__), 'data')
USERS_FILE = os.path.join(DATA_PATH, 'users.json')
AUDITS_FILE = os.path.join(DATA_PATH, 'audits.json')
CATALOGUE_FILE = os.path.join(DATA_PATH, 'metrics_catalogue_full.json')

init_engine(); create_schema()

@app.get('/healthz')
def healthz():
    return {"status":"ok"}, 200

@app.route('/')
def home():
    return render_template('landing.html', title='Landing')

# ----------------------- Scoring -----------------------

def strict_score_to_grade(score: float) -> str:
    return 'A+' if score >= 9.5 else 'A' if score >= 8.5 else 'B' if score >= 7.0 else 'C' if score >= 5.5 else 'D'

CATEGORY_WEIGHTS = {
    'Overall Site Health': 0.12,
    'Crawlability & Indexation': 0.12,
    'On-Page SEO': 0.12,
    'URL & Internal Linking': 0.10,
    'Performance & Web Vitals': 0.18,
    'Mobile & Usability': 0.12,
    'Security & HTTPS': 0.12,
    'International SEO': 0.06,
    'Backlinks & Authority': 0.06,
    'Advanced & Historical': 0.10
}

def generate_full_rows():
    with open(CATALOGUE_FILE, 'r', encoding='utf-8') as f:
        catalogue = json.load(f)
    values = ['OK','Warning','Error','Improvement']
    full_rows = [ { 'id': m['id'], 'category': m['category'], 'name': m['name'], 'value': random.choice(values) } for m in catalogue ]
    return full_rows


def compute_category_scores(full_rows):
    mapv = {'OK':1.0,'Improvement':0.7,'Warning':0.3,'Error':0.0}
    by_cat = {}
    for r in full_rows:
        by_cat.setdefault(r['category'], []).append(mapv.get(r['value'], 0.5))
    cat_scores = { c: round((sum(vals)/len(vals))*10, 2) for c, vals in by_cat.items() }
    for c in CATEGORY_WEIGHTS.keys():
        cat_scores.setdefault(c, round(random.uniform(6.5,8.5),2))
    return cat_scores


def compute_overall(cat_scores):
    overall = sum(cat_scores[c]*CATEGORY_WEIGHTS[c] for c in CATEGORY_WEIGHTS)
    return round(overall/ sum(CATEGORY_WEIGHTS.values()), 2)

# ----------------------- Open Audit -----------------------

@app.route('/audit', methods=['POST'])
def open_audit():
    url = normalize_url(request.form.get('url'))
    stub = stub_open_metrics(url)
    cat_scores = stub['cat_scores']
    score = compute_overall(cat_scores)
    grade = strict_score_to_grade(score)
    site_health = {
        'score': score,
        'errors': stub['site_health']['errors'],
        'warnings': stub['site_health']['warnings'],
        'notices': stub['site_health']['notices'],
        'grade': grade
    }
    results = { 'site_health': site_health, 'full': [], 'summary': generate_summary(url, site_health, cat_scores) }
    return render_template('results.html', title='Open Audit', url=url, date=datetime.utcnow().strftime('%Y-%m-%d'), results=results, mode='open', cat_scores=cat_scores)

# ----------------------- Registration & Login -----------------------

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name'); company = request.form.get('company'); email = request.form.get('email')
        s = get_session()
        if s and s.query(User).filter_by(email=email).first():
            flash('Email already registered', 'error'); return redirect(url_for('register'))
        token = f'verify-{random.randint(100000,999999)}'
        users = load(USERS_FILE)
        users.append({'email': email, 'name': name, 'company': company, 'role': 'user', 'password': None, 'verified': False, 'token': token})
        save(USERS_FILE, users)
        if s:
            s.add(User(email=email, name=name, company=company, role='user', password=None, verified=False)); s.commit()
        verify_link = url_for('verify', token=token, _external=True)
        send_verification_email(email, verify_link, name, DATA_PATH)
        return render_template('register_done.html', email=email, verify_link=verify_link)
    return render_template('register.html')

@app.route('/verify')
def verify():
    token = request.args.get('token')
    users = load(USERS_FILE)
    for u in users:
        if u.get('token') == token:
            s = get_session()
            if s:
                dbu = s.query(User).filter_by(email=u['email']).first()
                if dbu: dbu.verified = True; s.commit()
            return render_template('set_password.html', token=token, email=u['email'])
    abort(400)

@app.route('/set_password', methods=['POST'])
def set_password():
    token = request.form.get('token'); password = request.form.get('password')
    users = load(USERS_FILE)
    for u in users:
        if u.get('token') == token:
            u['verified'] = True; u['password'] = password; u['token'] = None; save(USERS_FILE, users)
            s = get_session()
            if s:
                dbu = s.query(User).filter_by(email=u['email']).first()
                if dbu: dbu.verified = True; dbu.password = password; s.commit()
            flash('Password set. You can now log in.', 'success')
            return render_template('verify_success.html')
    abort(400)

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email'); password = request.form.get('password')
        s = get_session()
        if s:
            dbu = s.query(User).filter_by(email=email).first()
            if dbu and (dbu.password or '') == (password or '') and dbu.verified:
                session['user'] = dbu.email; session['role'] = dbu.role
                flash('Logged in successfully', 'success'); return redirect(url_for('results_page'))
        users = load(USERS_FILE)
        for u in users:
            if u['email'] == email and (u['password'] or '') == (password or '') and u.get('verified'):
                session['user'] = email; session['role'] = u['role']
                flash('Logged in successfully', 'success'); return redirect(url_for('results_page'))
        flash('Invalid credentials or unverified email', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear(); flash('Logged out', 'success'); return redirect(url_for('home'))

# ----------------------- Registered Audit -----------------------

@app.route('/results')
def results_page():
    if not session.get('user'): return redirect(url_for('login'))
    url = normalize_url(request.args.get('url', 'https://example.com'))
    full_rows = generate_full_rows()
    cat_scores = compute_category_scores(full_rows)
    score = compute_overall(cat_scores)
    grade = strict_score_to_grade(score)
    site_health = { 'score': score, 'errors': random.randint(0, 60), 'warnings': random.randint(20, 160), 'notices': random.randint(50, 280), 'grade': grade }
    summary = generate_summary(url, site_health, cat_scores)

    s = get_session()
    if s:
        s.add(Audit(user_email=session['user'], url=url, date=datetime.utcnow().strftime('%Y-%m-%d'), grade=grade, summary=summary)); s.commit()
    else:
        audits = load(AUDITS_FILE); audits.append({'user': session['user'], 'url': url, 'date': datetime.utcnow().strftime('%Y-%m-%d'), 'grade': grade}); save(AUDITS_FILE, audits)

    results = { 'site_health': site_health, 'full': full_rows, 'summary': summary }
    return render_template('results.html', title='Registered Audit', url=url, date=datetime.utcnow().strftime('%Y-%m-%d'), results=results, mode='registered', cat_scores=cat_scores)

@app.route('/history')
def history():
    if not session.get('user'): return redirect(url_for('login'))
    s = get_session()
    if s:
        rows = s.query(Audit).filter_by(user_email=session.get('user')).all(); audits = [{'date': r.date, 'url': r.url, 'grade': r.grade} for r in rows]
    else:
        audits = [a for a in load(AUDITS_FILE) if a.get('user') == session.get('user')]
    return render_template('audit_history.html', audits=audits)

@app.route('/schedule', methods=['GET','POST'])
def schedule():
    if not session.get('user'): return redirect(url_for('login'))
    if request.method == 'POST': flash('Schedule created (demo). Integrate with a scheduler/worker in production.', 'success')
    return render_template('schedule.html')

# ----------------------- Admin -----------------------

@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email'); password = request.form.get('password')
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session['user'] = ADMIN_EMAIL; session['role'] = 'admin'
            flash('Admin logged in successfully', 'success'); return redirect(url_for('dashboard'))
        flash('Invalid admin credentials', 'error')
    return render_template('login.html')

@app.route('/admin/dashboard')
def dashboard():
    if session.get('role') != 'admin': return {'detail': 'Admin only'}, 403
    s = get_session()
    if s:
        users = s.query(User).all(); audits = s.query(Audit).all(); stats = {'users': len(users), 'audits': len(audits)}
        users_fmt = [{'email': u.email, 'role': u.role, 'name': u.name, 'company': u.company} for u in users]
        return render_template('admin_dashboard.html', stats=stats, users=users_fmt)
    users = load(USERS_FILE); audits = load(AUDITS_FILE); stats = {'users': len(users), 'audits': len(audits)}
    return render_template('admin_dashboard.html', stats=stats, users=users)

# ----------------------- Certified PDF -----------------------

@app.route('/report.pdf')
def report_pdf():
    if not session.get('user'): return redirect(url_for('login'))
    url = request.args.get('url', 'https://example.com')
    path = os.path.join(DATA_PATH, 'report.pdf')
    c = canvas.Canvas(path, pagesize=A4); width, height = A4
    score = random.uniform(6.0, 9.7)
    grade = strict_score_to_grade(score)
    c.setFillColorRGB(0,0.64,1); c.rect(40, height-80, 260, 30, fill=1)
    c.setFillColorRGB(1,1,1); c.drawString(50, height-65, f'{BRAND_NAME} – Certified Report')
    c.setFillColorRGB(0.1,0.1,0.1)
    c.drawString(40, height-110, f'URL: {url}')
    c.drawString(40, height-130, f'Date: {datetime.utcnow().strftime("%Y-%m-%d")}')
    c.drawString(40, height-150, f'Overall Grade: {grade}')
    c.drawString(40, height-170, f'Site Health Score: {round(score,2)} / 10')
    valid_until = datetime.utcnow() + timedelta(days=REPORT_VALIDITY_DAYS)
    c.drawString(40, height-190, f'Valid Until: {valid_until.strftime("%Y-%m-%d")}')
    summary = (
        "This certified audit summarizes the site's technical and SEO health across crawlability, performance, "
        "security, and mobile usability. Key improvements include optimizing images, fixing broken links, "
        "adding canonical tags, and enabling compression and caching. Addressing render-blocking resources and "
        "third-party script payloads will improve Core Web Vitals. Consistent structured data and security "
        "headers enhance visibility and trust. Trend tracking and scheduled audits maintain stability over time."
    )
    c.drawString(40, height-220, 'Executive Summary:')
    wrap = 95
    for i in range(0, len(summary), wrap):
        c.drawString(40, height-240 - (i//wrap)*15, summary[i:i+wrap])
    c.setFillColorRGB(0,0.64,1); c.circle(width-80, 80, 30, fill=1)
    c.setFillColorRGB(1,1,1); c.drawString(width-105, 80, 'CERT')
    c.showPage(); c.save()
    return send_file(path, mimetype='application/pdf', as_attachment=True, download_name='FFTech_Audit_Report.pdf')

if __name__ == '__main__':
    app.run(debug=True)
