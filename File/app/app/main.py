
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_file
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from passlib.hash import bcrypt
from datetime import datetime, timedelta
import threading, time, os, pytz

from .models import db, User, Website, Audit, AuditMetric
from .audit_engine.engine import run_all, compute_score, run_all_basic, compute_score_basic
from .metrics.summary import generate_summary
from .reporting import render_pdf
from .email_utils import send_email

app = Flask(__name__, template_folder='../templates')

SECRET_KEY = os.getenv('SECRET_KEY', 'change-this')
app.config['SECRET_KEY'] = SECRET_KEY

db_url = os.getenv('DATABASE_URL')
if not db_url:
    raise RuntimeError('DATABASE_URL is not set. Add a variable reference from Railway Postgres.')
if db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'connect_args': {'sslmode': os.getenv('DB_SSLMODE', 'require')}}

db.init_app(app)
serializer = URLSafeTimedSerializer(SECRET_KEY)
FREE_AUDITS = 10

@app.context_processor
def inject_year():
    return {'year': datetime.utcnow().year}

def current_user():
    uid = session.get('uid')
    if not uid:
        return None
    return db.session.get(User, uid)

def login_required_html(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for('login_view'))
        return f(*args, **kwargs)
    return wrapper

def generate_token(user_id: int):
    return serializer.dumps({'uid': user_id})

def verify_token(token: str, max_age: int = 7*24*3600):
    try:
        data = serializer.loads(token, max_age=max_age)
        return data.get('uid')
    except (SignatureExpired, BadSignature):
        return None

# ---------- Open Audit (Public) ----------
@app.get('/open-audit')
def open_audit_form():
    return render_template('open_audit.html')

@app.post('/open-audit/run')
def open_audit_run():
    url = request.form.get('url')
    if not url:
        return render_template('open_audit_result.html', error='Please provide a URL.')
    # Basic run; do NOT persist
    metrics = run_all_basic(url)
    score, grade = compute_score_basic(metrics)
    summary = generate_summary(metrics, score, grade, url)
    top_issues = []
    c = metrics.get('Crawlability & Indexation', {})
    if c.get('broken_internal_links',0) or c.get('broken_external_links',0):
        top_issues.append('Broken links detected')
    s = metrics.get('Security & HTTPS', {})
    if not s.get('https', True):
        top_issues.append('HTTPS not enforced')
    p = metrics.get('Technical & Performance', {})
    if p.get('total_page_size_mb',0) and p.get('total_page_size_mb',0) > 3:
        top_issues.append('Heavy page size')
    return render_template('open_audit_result.html', url=url, score=score, grade=grade, summary=summary, top_issues=top_issues, metrics=metrics)

# ---------- Public Landing ----------
@app.get('/')
def landing():
    return render_template('landing.html')

# ---------- Auth ----------
@app.route('/login', methods=['GET','POST'])
def login_view():
    error = None
    if request.method == 'POST':
        email = request.form.get('email'); password = request.form.get('password')
        u = db.session.query(User).filter_by(email=email).first()
        if not u or not bcrypt.verify(password, u.password_hash):
            error = 'Invalid credentials'
        elif not u.email_confirmed:
            error = 'Email not confirmed'
        else:
            session['uid'] = u.id
            return redirect(url_for('dashboard'))
    return render_template('login.html', error=error)

@app.get('/logout')
def logout():
    session.pop('uid', None)
    return redirect(url_for('landing'))

@app.route('/register', methods=['GET','POST'])
def register_view():
    message = None
    if request.method == 'POST':
        email = request.form.get('email'); name = request.form.get('name'); password = request.form.get('password'); confirm = request.form.get('confirm')
        if not email or not name or not password or password != confirm:
            message = 'Provide name, email and matching passwords'
        elif db.session.query(User).filter_by(email=email).first():
            message = 'Email already registered'
        else:
            u = User(email=email, name=name, password_hash=bcrypt.hash(password))
            db.session.add(u); db.session.commit()
            token = generate_token(u.id)
            confirm_link = f"{request.host_url.rstrip('/')}/auth/confirm?token={token}"
            email_body = f"""Hello {name},

Please confirm your account by clicking the link below:

{confirm_link}

Thanks,
FF Tech
"""
            send_email(email, 'Confirm your FF Tech account', email_body)
            return render_template('register_done.html', email=email)
    return render_template('register.html', message=message)

@app.get('/auth/confirm')
def confirm():
    token = request.args.get('token')
    uid = verify_token(token)
    if not uid:
        return render_template('verify_success.html')
    u = db.session.get(User, uid)
    if u:
        u.email_confirmed = True; db.session.commit()
    return render_template('verify_success.html')

# ---------- Registered User Module ----------
@app.get('/dashboard')
@login_required_html
def dashboard():
    u = current_user()
    websites = db.session.query(Website).filter((Website.user_id==u.id)).order_by(Website.id.desc()).all()
    audit = db.session.query(Audit).filter_by(user_id=u.id).order_by(Audit.id.desc()).first()
    return render_template('dashboard.html', websites=websites, audit=audit, subscribed=bool(u.subscription_active))

@app.post('/websites/add')
@login_required_html
def add_website_html():
    u = current_user()
    url = request.form.get('url')
    if not url:
        return redirect(url_for('dashboard'))
    w = Website(user_id=u.id, url=url); db.session.add(w); db.session.commit()
    return redirect(url_for('dashboard'))

@app.post('/audits/run')
@login_required_html
def run_audit_html():
    u = current_user()
    website_id = request.form.get('website_id', type=int)
    w = db.session.get(Website, website_id)
    if not w or w.user_id != u.id:
        return redirect(url_for('dashboard'))
    if not u.subscription_active and u.free_audits_used >= FREE_AUDITS:
        return redirect(url_for('dashboard'))

    audit = Audit(website_id=w.id, user_id=u.id)
    db.session.add(audit); db.session.commit()

    metrics = run_all(w.url)
    score, grade = compute_score(metrics)
    audit.health_score = score; audit.grade = grade

    errors = 0; warnings = 0
    for cat, vals in metrics.items():
        if isinstance(vals, dict):
            for k, v in vals.items():
                level = 'info'
                if k.startswith('broken_') and isinstance(v, int) and v > 0:
                    level = 'error'; errors += v
                elif isinstance(v, str) and v == 'missing':
                    level = 'warning'; warnings += 1
                am = AuditMetric(audit_id=audit.id, category=cat, key=k, value=str(v), level=level)
                db.session.add(am)
    audit.errors = errors; audit.warnings = warnings; audit.notices = 0

    summary = generate_summary(metrics, score, grade, w.url)
    audit.summary = summary
    pdf_path = render_pdf(audit, metrics, w.url)
    audit.pdf_path = pdf_path; audit.completed_at = datetime.utcnow(); db.session.commit()

    if not u.subscription_active:
        u.free_audits_used += 1; db.session.commit()

    try:
        send_email(u.email, 'FF Tech Daily Audit Snapshot', summary, attachments=[pdf_path])
    except Exception:
        pass

    return redirect(url_for('dashboard'))

@app.get('/history')
@login_required_html
def history():
    u = current_user()
    audits = db.session.query(Audit).filter_by(user_id=u.id).order_by(Audit.id.desc()).all()
    for a in audits:
        a.website = db.session.get(Website, a.website_id)
    return render_template('audit_history.html', audits=audits)

@app.get('/download/<int:audit_id>')
@login_required_html
def download_pdf(audit_id):
    a = db.session.get(Audit, audit_id)
    if not a or a.user_id != current_user().id or not a.pdf_path:
        return redirect(url_for('dashboard'))
    return send_file(a.pdf_path, as_attachment=True)

@app.route('/schedule', methods=['GET','POST'])
@login_required_html
def schedule_view():
    u = current_user()
    if request.method == 'POST':
        time_str = request.form.get('time'); tz = request.form.get('timezone'); enabled = request.form.get('enabled') == 'on'
        u.schedule_enabled = enabled; u.schedule_time = time_str; u.schedule_timezone = tz
        if enabled and time_str and tz:
            try:
                hour, minute = map(int, time_str.split(':'))
                zone = pytz.timezone(tz)
                now = datetime.now(zone)
                next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if next_run <= now:
                    next_run = next_run + timedelta(days=1)
                u.next_run_at = next_run.astimezone(pytz.UTC)
            except Exception:
                u.next_run_at = None
        else:
            u.next_run_at = None
        db.session.commit(); return redirect(url_for('schedule_view'))
    return render_template('schedule.html', time=u.schedule_time, timezone=u.schedule_timezone, enabled=u.schedule_enabled, next_run_at_utc=(u.next_run_at.isoformat() if u.next_run_at else None))

# ---------- Scheduler ----------
stop_flag = False

def scheduler_loop(app):
    with app.app_context():
        while not stop_flag:
            now_utc = datetime.utcnow()
            users = db.session.query(User).filter(User.schedule_enabled == True, User.next_run_at != None).all()
            for u in users:
                if u.next_run_at and u.next_run_at <= now_utc:
                    webs = db.session.query(Website).filter_by(user_id=u.id).all()
                    for w in webs:
                        audit = Audit(website_id=w.id, user_id=u.id)
                        db.session.add(audit); db.session.commit()
                        metrics = run_all(w.url)
                        score, grade = compute_score(metrics)
                        audit.health_score = score; audit.grade = grade
                        errors = 0; warnings = 0
                        for cat, vals in metrics.items():
                            if isinstance(vals, dict):
                                for k, v in vals.items():
                                    level = 'info'
                                    if k.startswith('broken_') and isinstance(v, int) and v > 0:
                                        level = 'error'; errors += v
                                    elif isinstance(v, str) and v == 'missing':
                                        level = 'warning'; warnings += 1
                                    am = AuditMetric(audit_id=audit.id, category=cat, key=k, value=str(v), level=level)
                                    db.session.add(am)
                        audit.errors = errors; audit.warnings = warnings; audit.notices = 0
                        summary = generate_summary(metrics, score, grade, w.url)
                        audit.summary = summary
                        pdf_path = render_pdf(audit, metrics, w.url)
                        audit.pdf_path = pdf_path; audit.completed_at = datetime.utcnow(); db.session.commit()
                    try:
                        zone = pytz.timezone(u.schedule_timezone or 'UTC')
                        hour, minute = map(int, (u.schedule_time or '00:00').split(':'))
                        next_local = pytz.utc.localize(now_utc).astimezone(zone).replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=1)
                        u.next_run_at = next_local.astimezone(pytz.UTC); db.session.commit()
                    except Exception:
                        u.next_run_at = None; db.session.commit()
                    try:
                        send_email(u.email, 'FF Tech Daily Audit', summary, attachments=[pdf_path])
                    except Exception:
                        pass
            time.sleep(60)

scheduler_started = False

def init_db_and_scheduler_once():
    global scheduler_started
    if scheduler_started:
        return
    with app.app_context():
        db.create_all()
        t = threading.Thread(target=scheduler_loop, args=(app,), daemon=True)
        t.start()
        scheduler_started = True

init_db_and_scheduler_once()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '8080')))
