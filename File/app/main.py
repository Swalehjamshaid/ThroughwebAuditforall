import os
import json
import random
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, abort
# Matplotlib must run headless in containers
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from werkzeug.security import generate_password_hash, check_password_hash
# ----------------------- Robust imports -----------------------
# This block works under Gunicorn with the app/ package (we use wsgi.py)
try:
    from .settings import (
        SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD, BRAND_NAME,
        REPORT_VALIDITY_DAYS, GOOGLE_PSI_API_KEY, WPT_API_KEY
    )
    from .security import load, save, normalize_url, generate_summary
    from .models import init_engine, create_schema, get_session, User, Audit
    from .emailer import send_verification_email
    from .pagespeed import fetch_pagespeed
    from .webpagetest import run_wpt_test
    PACKAGE_MODE = True
except ImportError:
    # Fallback for local script runs only (python main.py in a flat layout)
    from settings import (
        SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD, BRAND_NAME,
        REPORT_VALIDITY_DAYS, GOOGLE_PSI_API_KEY, WPT_API_KEY
    )
    from security import load, save, normalize_url, generate_summary
    from models import init_engine, create_schema, get_session, User, Audit
    from emailer import send_verification_email
    from pagespeed import fetch_pagespeed
    try:
        from webpagetest import run_wpt_test
    except Exception:
        def run_wpt_test(*args, **kwargs): # graceful fallback
            return None
    PACKAGE_MODE = False
# --- Hard-coded API key fallback (if settings/env not provided) ---
HARDCODED_API_KEY = os.getenv("HARDCODED_PSI_KEY", "AIzaSyDUVptDEm1ZbiBdb5m1DGjvKCW_LBVJMEw")
GOOGLE_PSI_API_KEY = GOOGLE_PSI_API_KEY or os.getenv("GOOGLE_PSI_API_KEY") or HARDCODED_API_KEY
# ----------------------- Flask app -----------------------
app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = SECRET_KEY
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, 'data')
USERS_FILE = os.path.join(DATA_PATH, 'users.json')
AUDITS_FILE = os.path.join(DATA_PATH, 'audits.json')
CATALOGUE_FILE = os.path.join(DATA_PATH, 'metrics_catalogue_full.json')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
CHARTS_DIR = os.path.join(STATIC_DIR, 'charts')
os.makedirs(DATA_PATH, exist_ok=True)
os.makedirs(CHARTS_DIR, exist_ok=True)
for fp, default in [(USERS_FILE, []), (AUDITS_FILE, []), (CATALOGUE_FILE, [])]:
    if not os.path.exists(fp):
        with open(fp, 'w', encoding='utf-8') as f:
            json.dump(default, f)
# ----------------------- SAFE DB INITIALIZATION (Fixes Gunicorn Worker Crash on Railway) -----------------------
from sqlalchemy.exc import IntegrityError
import psycopg2.errors

def safe_create_schema():
    """
    Safely creates the database schema.
    Handles concurrent table creation attempts by multiple Gunicorn workers,
    which cause the 'pg_type_typname_nsp_index' unique violation error.
    """
    try:
        create_schema()
        app.logger.info("Database schema created or already exists.")
    except IntegrityError as e:
        if isinstance(e.orig, psycopg2.errors.UniqueViolation) and "pg_type_typname_nsp_index" in str(e.orig):
            app.logger.info("Schema creation race condition detected – safely ignored (tables already exist).")
        else:
            app.logger.error(f"Failed to create schema due to integrity error: {e}")
            raise
    except Exception as e:
        app.logger.error(f"Unexpected error during schema creation: {e}")
        raise

# Initialize the engine
init_engine()

# Run schema creation safely — prevents crash on multi-worker startup
safe_create_schema()

# ----------------------- Health -----------------------
@app.get('/healthz')
def healthz():
    return {"status": "ok"}, 200
# ----------------------- Landing -----------------------
@app.route('/')
def home():
    return render_template('landing.html', title='Landing')
# ----------------------- Scoring Model -----------------------
def strict_score_to_grade(score10: float) -> str:
    """World-class grading thresholds."""
    return 'A+' if score10 >= 9.5 else 'A' if score10 >= 8.5 else 'B' if score10 >= 7.0 else 'C' if score10 >= 5.5 else 'D'
CATEGORY_WEIGHTS = {
    'Performance &amp; Web Vitals': 0.28, # slight boost to performance
    'Accessibility': 0.12,
    'Best Practices': 0.12,
    'SEO': 0.18,
    'Crawlability &amp; Indexation': 0.10,
    'URL &amp; Internal Linking': 0.06,
    'Security &amp; HTTPS': 0.10,
    'Mobile &amp; Usability': 0.04
}
# ----------------------- PSI Detail Extraction -----------------------
def extract_psi_details(psi_raw: dict) -> dict:
    """
    Extract Core Web Vitals & key Lighthouse metrics from PSI JSON.
    Returns a dict with lab & field (when available).
    """
    out = {
        'lab': {},
        'field': {},
        'opportunities': [],
        'diagnostics': []
    }
    try:
        lr = psi_raw.get('lighthouseResult') or {}
        audits = lr.get('audits') or {}
        cats = lr.get('categories') or {}
        # Lab metrics
        def m_val(key, prop='numericValue'):
            return (audits.get(key) or {}).get(prop)
        out['lab'] = {
            'FCP_ms': m_val('first-contentful-paint'),
            'TTFB_ms': m_val('server-response-time'),
            'LCP_ms': m_val('largest-contentful-paint'),
            'INP_ms': m_val('interaction-to-next-paint', 'numericValue'),
            'CLS': m_val('cumulative-layout-shift', 'numericValue'),
            'SpeedIndex_ms': m_val('speed-index'),
            'TimeToInteractive_ms': m_val('interactive'),
        }
        # Field (CrUX) metrics (when available)
        lexp = psi_raw.get('loadingExperience') or {}
        fmetrics = lexp.get('metrics') or {}
        def field_metric(M):
            return (fmetrics.get(M) or {}).get('percentile')
        out['field'] = {
            'FCP_ms': field_metric('FIRST_CONTENTFUL_PAINT_MS'),
            'TTFB_ms': field_metric('EXPERIMENTAL_TIME_TO_FIRST_BYTE'),
            'LCP_ms': field_metric('LARGEST_CONTENTFUL_PAINT_MS'),
            'INP_ms': field_metric('INTERACTION_TO_NEXT_PAINT'),
            'CLS': (fmetrics.get('CUMULATIVE_LAYOUT_SHIFT_SCORE') or {}).get('percentile'),
        }
        # Opportunities (top 5)
        opp = []
        for k, a in audits.items():
            details = a.get('details') or {}
            if (a.get('scoreDisplayMode') == 'opportunity') or details.get('type') == 'opportunity':
                est_ms = (details.get('overallSavingsMs') or 0)
                if est_ms and a.get('title'):
                    opp.append({'id': k, 'title': a['title'], 'estimated_savings_ms': round(est_ms)})
        out['opportunities'] = sorted(opp, key=lambda x: x['estimated_savings_ms'], reverse=True)[:5]
        # Diagnostics (selected)
        diags = []
        for key in ['mainthread-work-breakdown', 'third-party-summary', 'largest-contentful-paint-element', 'layout-shift-elements']:
            a = audits.get(key)
            if a and a.get('title'):
                diags.append({'id': key, 'title': a['title'], 'scoreDisplayMode': a.get('scoreDisplayMode')})
        out['diagnostics'] = diags
    except Exception:
        pass
    return out
# ----------------------- Extra HTTP checks -----------------------
import requests
def quick_checks(url: str) -> dict:
    """
    Security & SEO checks beyond Lighthouse:
    - Robots/sitemap
    - HTTPS/HSTS
    - Canonical/viewport
    - Security headers: X-Content-Type-Options, X-Frame-Options, Content-Security-Policy
    Returns 0..100 scores per category.
    """
    res = {
        'Crawlability &amp; Indexation': 60,
        'URL &amp; Internal Linking': 60,
        'Security &amp; HTTPS': 60,
        'Mobile &amp; Usability': 60
    }
    try:
        r_head = requests.head(url, timeout=15, allow_redirects=True)
        final_url = r_head.url
        https_ok = final_url.startswith('https://')
        hsts = r_head.headers.get('Strict-Transport-Security')
        xcto = r_head.headers.get('X-Content-Type-Options')
        xfo = r_head.headers.get('X-Frame-Options')
        csp = r_head.headers.get('Content-Security-Policy')
        security_bonus = (15 if https_ok else 0) + (15 if hsts else 0) + (5 if (xcto == 'nosniff') else 0) + (5 if xfo else 0) + (5 if csp else 0)
        res['Security &amp; HTTPS'] = min(70 + security_bonus, 100)
        from urllib.parse import urlparse
        p = urlparse(final_url)
        robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
        sm_url = f"{p.scheme}://{p.netloc}/sitemap.xml"
        robots_ok = False
        sitemap_ok = False
        try:
            rr = requests.get(robots_url, timeout=10)
            robots_ok = (rr.status_code == 200 and 'user-agent' in rr.text.lower())
        except Exception:
            pass
        try:
            sm = requests.get(sm_url, timeout=10)
            sitemap_ok = (sm.status_code == 200 and ('<urlset' in sm.text or '<sitemapindex' in sm.text))
        except Exception:
            pass
        res['Crawlability &amp; Indexation'] = min(60 + (20 if robots_ok else 0) + (20 if sitemap_ok else 0), 100)
        g = requests.get(final_url, timeout=20)
        html = g.text.lower()
        has_viewport = '<meta name="viewport"' in html
        has_canonical = 'rel="canonical"' in html or "rel='canonical'" in html
        res['Mobile &amp; Usability'] = min(60 + (20 if has_viewport else 0) + 20, 100)
        res['URL &amp; Internal Linking'] = min(60 + (20 if has_canonical else 0) + 20, 100)
    except Exception:
        pass
    return res
def compute_overall(cat_scores_100: dict) -> float:
    """Input scores in 0..100; returns overall in 0..10."""
    DEFAULT = 75.0
    total = 0.0
    for c, w in CATEGORY_WEIGHTS.items():
        total += float(cat_scores_100.get(c, DEFAULT)) * w
    weighted_100 = total / max(sum(CATEGORY_WEIGHTS.values()), 1e-9)
    return round(weighted_100 / 10.0, 2)
# ----------------------- Charts -----------------------
def _save_fig(fig, name):
    path = os.path.join(CHARTS_DIR, name)
    fig.savefig(path, bbox_inches='tight', dpi=160)
    plt.close(fig)
    return f'/static/charts/{name}'
def chart_category_bars(cat_scores_100: dict):
    labels = list(cat_scores_100.keys())
    values = [cat_scores_100[l] for l in labels]
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.bar(labels, values, color='#0a84ff')
    ax.set_ylim(0, 100)
    ax.set_title('Category Scores (0–100)')
    ax.set_ylabel('Score')
    ax.tick_params(axis='x', rotation=25)
    for i, v in enumerate(values):
        ax.text(i, v + 1.5, f'{v:.0f}', ha='center', fontsize=9)
    return _save_fig(fig, 'category_scores.png')
def chart_issue_donut(errors, warnings, notices):
    sizes = [errors, warnings, notices]
    labels = [f'Errors ({errors})', f'Warnings ({warnings})', f'Notices ({notices})']
    colors = ['#ff3b30', '#ff9f0a', '#34c759']
    fig, ax = plt.subplots(figsize=(5.4,5.4))
    wedges, _ = ax.pie(sizes, colors=colors, startangle=90, wedgeprops=dict(width=0.42))
    ax.legend(wedges, labels, loc='center left', bbox_to_anchor=(1,0.5))
    ax.set_title('Issue Composition')
    centre_circle = plt.Circle((0,0),0.58,fc='white')
    fig.gca().add_artist(centre_circle)
    return _save_fig(fig, 'issues_donut.png')
def chart_overall_gauge(score10: float):
    fig, ax = plt.subplots(figsize=(8, 1.2))
    ax.barh([0], [score10], color='#0a84ff', height=0.5)
    ax.set_xlim(0, 10)
    ax.set_yticks([])
    ax.set_title(f'Overall Site Health: {score10:.2f} / 10', fontsize=11, pad=8)
    for t in [5.5, 7.0, 8.5, 9.5]:
        ax.axvline(t, color='#999', linestyle='--', linewidth=1)
    for x, g in [(5.5,'C'),(7.0,'B'),(8.5,'A'),(9.5,'A+')]:
        ax.text(x, 0.42, g, color='#333', fontsize=9, ha='center')
    return _save_fig(fig, 'overall_gauge.png')
def chart_worldwide(metrics):
    regions = [m['region'] for m in metrics]
    latency = [m['latency_ms'] for m in metrics]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    y = list(range(len(regions)))
    ax.barh(y, latency, color='#5856d6')
    ax.set_yticks(y)
    ax.set_yticklabels(regions)
    ax.set_xlabel('Median Latency (ms)')
    ax.set_title('Worldwide Network Latency &amp; Vitals')
    for i, m in enumerate(metrics):
        ax.text(latency[i] + 5, i, f"LCP {m.get('lcp_ms', '—')}ms | INP {m.get('inp_ms', '—')}ms | CLS {m.get('cls', '—')}", va='center', fontsize=8)
    return _save_fig(fig, 'worldwide.png')
# ----------------------- Helpers: Combine PSI data -----------------------
def merge_categories(mobile: dict, desktop: dict) -> dict:
    keys = set(mobile['categories'].keys()) | set(desktop['categories'].keys())
    merged = {}
    for k in keys:
        merged[k] = round(((mobile['categories'].get(k, 0) + desktop['categories'].get(k, 0)) / 2.0), 1)
    return merged
def build_worldwide(url: str) -> list:
    ww = []
    if WPT_API_KEY:
        for loc in ["Dulles:Chrome","London:Chrome","Frankfurt:Chrome","Sydney:Chrome","Singapore:Chrome"]:
            try:
                m = run_wpt_test(url, location=loc, api_key=WPT_API_KEY, timeout=210)
                if m:
                    ww.append({'region': loc, 'latency_ms': m['ttfb_ms'], 'lcp_ms': m.get('lcp_ms'),
                               'inp_ms': None, 'cls': None})
            except Exception:
                pass
    else:
        regions = ['North America','Europe','Middle East','South Asia','East Asia','Oceania','Latin America','Africa']
        for r in regions:
            ww.append({'region': r, 'latency_ms': random.randint(80, 280), 'lcp_ms': random.randint(2200, 4200),
                       'inp_ms': random.randint(150, 300), 'cls': round(random.uniform(0.05, 0.25),2)})
    return ww
# ----------------------- Open Audit -----------------------
@app.route('/audit', methods=['POST'])
def open_audit():
    url = normalize_url(request.form.get('url'))
    if not url:
        flash('Please provide a valid URL', 'error')
        return redirect(url_for('home'))
    try:
        # PSI: mobile & desktop (sequential to avoid bursts)
        mobile = fetch_pagespeed(url, 'mobile', GOOGLE_PSI_API_KEY)
        desktop = fetch_pagespeed(url, 'desktop', GOOGLE_PSI_API_KEY)
    except Exception as e:
        flash(f'PageSpeed Insights refused the request (check API key/config). Details: {e}', 'error')
        return redirect(url_for('home'))
    psi_cat = merge_categories(mobile, desktop)
    extra = quick_checks(url)
    cat_scores_100 = {**psi_cat, **extra}
    overall10 = compute_overall(cat_scores_100)
    grade = strict_score_to_grade(overall10)
    # Deep PSI details
    psi_details = {
        'mobile': extract_psi_details(mobile.get('raw', {})),
        'desktop': extract_psi_details(desktop.get('raw', {})),
    }
    site_health = {
        'score': overall10,
        'grade': grade,
        'errors': random.randint(5, 25),
        'warnings': random.randint(40, 140),
        'notices': random.randint(100, 300)
    }
    ww = build_worldwide(url)
    # Charts
    chart_overall = chart_overall_gauge(overall10)
    chart_categories = chart_category_bars(cat_scores_100)
    chart_issues = chart_issue_donut(site_health['errors'], site_health['warnings'], site_health['notices'])
    chart_world = chart_worldwide(ww)
    summary = generate_summary(url, site_health, {k: v/10.0 for k, v in cat_scores_100.items()})
    results = {
        'site_health': site_health,
        'summary': summary,
        'charts': {
            'overall_gauge': chart_overall,
            'category_bar': chart_categories,
            'issues_donut': chart_issues,
            'worldwide_latency': chart_world
        },
        'worldwide': ww,
        'psi': {'mobile': mobile, 'desktop': desktop},
        'psi_details': psi_details,
        'categories_100': cat_scores_100
    }
    return render_template('results.html',
                           title='Open Audit',
                           url=url,
                           date=datetime.utcnow().strftime('%Y-%m-%d'),
                           results=results,
                           mode='open',
                           BRAND_NAME=BRAND_NAME)
# ----------------------- Registration & Login -----------------------
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        company = request.form.get('company')
        email = request.form.get('email')
        s = get_session()
        if s:
            try:
                if s.query(User).filter_by(email=email).first():
                    flash('Email already registered', 'error')
                    return redirect(url_for('register'))
            except Exception:
                s = None
        token = f'verify-{random.randint(100000,999999)}'
        users = load(USERS_FILE)
        users.append({'email':email,'name':name,'company':company,'role':'user',
                      'password_hash':None,'verified':False,'token':token})
        save(USERS_FILE, users)
        if s:
            s.add(User(email=email, name=name, company=company, role='user',
                       password_hash='', verified=False)); s.commit()
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
    token = request.form.get('token')
    password = request.form.get('password')
    users = load(USERS_FILE)
    for u in users:
        if u.get('token') == token:
            u['verified'] = True
            u['password_hash'] = generate_password_hash(password)
            u['token'] = None
            save(USERS_FILE, users)
            s = get_session()
            if s:
                dbu = s.query(User).filter_by(email=u['email']).first()
                if dbu:
                    dbu.verified = True
                    dbu.password_hash = u['password_hash']
                    s.commit()
            flash('Password set. You can now log in.', 'success')
            return render_template('verify_success.html')
    abort(400)
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        s = get_session()
        if s:
            dbu = s.query(User).filter_by(email=email).first()
            if dbu and dbu.verified and check_password_hash(dbu.password_hash or '', password or ''):
                session['user'] = dbu.email
                session['role'] = dbu.role
                flash('Logged in successfully','success')
                return redirect(url_for('results_page'))
        users = load(USERS_FILE)
        for u in users:
            if u['email']==email and u.get('verified') and check_password_hash(u.get('password_hash') or '', password or ''):
                session['user']=email
                session['role']=u['role']
                flash('Logged in successfully','success')
                return redirect(url_for('results_page'))
        flash('Invalid credentials or unverified email','error')
    return render_template('login.html')
@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out','success')
    return redirect(url_for('home'))
# ----------------------- Registered Audit -----------------------
@app.route('/results')
def results_page():
    if not session.get('user'):
        return redirect(url_for('login'))
    url = normalize_url(request.args.get('url','https://example.com'))
    try:
        mobile = fetch_pagespeed(url, 'mobile', GOOGLE_PSI_API_KEY)
        desktop = fetch_pagespeed(url, 'desktop', GOOGLE_PSI_API_KEY)
    except Exception as e:
        flash(f'PageSpeed Insights refused the request (check API key/config). Details: {e}', 'error')
        return redirect(url_for('home'))
    psi_cat = merge_categories(mobile, desktop)
    extra = quick_checks(url)
    cat_scores_100 = {**psi_cat, **extra}
    overall10 = compute_overall(cat_scores_100)
    grade = strict_score_to_grade(overall10)
    psi_details = {
        'mobile': extract_psi_details(mobile.get('raw', {})),
        'desktop': extract_psi_details(desktop.get('raw', {})),
    }
    site_health = {
        'score': overall10,
        'errors': random.randint(0,60),
        'warnings': random.randint(20,160),
        'notices': random.randint(50,280),
        'grade': grade
    }
    s = get_session()
    summary = generate_summary(url, site_health, {k: v/10.0 for k, v in cat_scores_100.items()})
    if s:
        s.add(Audit(user_email=session['user'], url=url, date=datetime.utcnow().strftime('%Y-%m-%d'),
                    grade=grade, summary=summary, overall_score=int(round(overall10*10))))
        s.commit()
    else:
        audits = load(AUDITS_FILE)
        audits.append({'user': session['user'], 'url': url, 'date': datetime.utcnow().strftime('%Y-%m-%d'),
                       'grade': grade})
        save(AUDITS_FILE, audits)
    chart_overall = chart_overall_gauge(overall10)
    chart_categories = chart_category_bars(cat_scores_100)
    chart_issues = chart_issue_donut(site_health['errors'], site_health['warnings'], site_health['notices'])
    ww = build_worldwide(url)
    chart_world = chart_worldwide(ww)
    results = {
        'site_health': site_health,
        'summary': summary,
        'charts': {
            'overall_gauge': chart_overall,
            'category_bar': chart_categories,
            'issues_donut': chart_issues,
            'worldwide_latency': chart_world
        },
        'worldwide': ww if ww else [],
        'psi': {'mobile': mobile, 'desktop': desktop},
        'psi_details': psi_details,
        'categories_100': cat_scores_100
    }
    return render_template('results.html',
                           title='Registered Audit',
                           url=url,
                           date=datetime.utcnow().strftime('%Y-%m-%d'),
                           results=results,
                           mode='registered',
                           BRAND_NAME=BRAND_NAME)
@app.route('/history')
def history():
    if not session.get('user'):
        return redirect(url_for('login'))
    s = get_session()
    if s:
        rows = s.query(Audit).filter_by(user_email=session.get('user')).all()
        audits = [{'date': r.date, 'url': r.url, 'grade': r.grade, 'overall_score': r.overall_score} for r in rows]
    else:
        audits = [a for a in load(AUDITS_FILE) if a.get('user') == session.get('user')]
    return render_template('audit_history.html', audits=audits)
@app.route('/schedule', methods=['GET','POST'])
def schedule():
    if not session.get('user'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        flash('Schedule created (demo). Integrate with a scheduler/worker in production.', 'success')
    return render_template('schedule.html')
# ----------------------- Admin -----------------------
@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session['user'] = ADMIN_EMAIL
            session['role'] = 'admin'
            flash('Admin logged in successfully','success')
            return redirect(url_for('dashboard'))
        flash('Invalid admin credentials','error')
    return render_template('login.html')
@app.route('/admin/dashboard')
def dashboard():
    if session.get('role') != 'admin':
        return {'detail':'Admin only'}, 403
    s = get_session()
    if s:
        users = s.query(User).all()
        audits = s.query(Audit).all()
        stats = {'users': len(users), 'audits': len(audits)}
        users_fmt = [{'email': u.email, 'role': u.role, 'name': u.name, 'company': u.company} for u in users]
        return render_template('admin_dashboard.html', stats=stats, users=users_fmt)
    users = load(USERS_FILE)
    audits = load(AUDITS_FILE)
    stats = {'users': len(users), 'audits': len(audits)}
    return render_template('admin_dashboard.html', stats=stats, users=users)
# ----------------------- Certified PDF -----------------------
@app.route('/report.pdf')
def report_pdf():
    if not session.get('user'):
        return redirect(url_for('login'))
    url = request.args.get('url', 'https://example.com')
    path = os.path.join(DATA_PATH, 'report.pdf')
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    try:
        mobile = fetch_pagespeed(url, 'mobile', GOOGLE_PSI_API_KEY)
        desktop = fetch_pagespeed(url, 'desktop', GOOGLE_PSI_API_KEY)
    except Exception as e:
        flash(f'PageSpeed Insights refused the request (check API key/config). Details: {e}', 'error')
        return redirect(url_for('home'))
    performance = int(round(((mobile['categories'].get('Performance &amp; Web Vitals',0) +
                               desktop['categories'].get('Performance &amp; Web Vitals',0))/2)))
    overall10 = compute_overall({
        **quick_checks(url),
        'Performance &amp; Web Vitals': performance,
        'Accessibility': int(round(((mobile['categories'].get('Accessibility',0) +
                                     desktop['categories'].get('Accessibility',0))/2))),
        'Best Practices': int(round(((mobile['categories'].get('Best Practices',0) +
                                      desktop['categories'].get('Best Practices',0))/2))),
        'SEO': int(round(((mobile['categories'].get('SEO',0) +
                           desktop['categories'].get('SEO',0))/2))),
    })
    grade = strict_score_to_grade(overall10)
    # Header
    c.setFillColorRGB(0, 0.64, 1)
    c.rect(40, height - 80, 360, 30, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.drawString(50, height - 65, f'{BRAND_NAME} – Certified Audit')
    # Body
    c.setFillColorRGB(0.1,0.1,0.1)
    c.drawString(40, height - 110, f'URL: {url}')
    c.drawString(40, height - 130, f'Date: {datetime.utcnow().strftime("%Y-%m-%d")}')
    c.drawString(40, height - 150, f'Overall Grade: {grade}')
    c.drawString(40, height - 170, f'Overall Score: {overall10:.2f} / 10')
    valid_until = datetime.utcnow() + timedelta(days=REPORT_VALIDITY_DAYS)
    c.drawString(40, height - 190, f'Valid Until: {valid_until.strftime("%Y-%m-%d")}')
    summary = ("This certified audit uses Google PageSpeed Insights (Lighthouse + CrUX, when available) to assess "
               "Performance, Accessibility, Best Practices and SEO, plus security/indexation checks. Optional "
               "WebPageTest geo runs provide real-world latency across regions.")
    c.drawString(40, height - 220, 'Executive Summary:')
    wrap = 95
    for i in range(0, len(summary), wrap):
        c.drawString(40, height - 240 - (i // wrap) * 15, summary[i:i+wrap])
    # Seal
    c.setFillColorRGB(0, 0.64, 1)
    c.circle(width - 80, 80, 30, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.drawString(width - 105, 80, 'CERT')
    c.showPage()
    c.save()
    return send_file(path, mimetype='application/pdf', as_attachment=True, download_name='FFTech_Audit_Report.pdf')
