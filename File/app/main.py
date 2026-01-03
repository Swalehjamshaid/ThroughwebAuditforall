import os, json, smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from flask import (
    Flask, render_template, render_template_string,
    request, redirect, url_for, session, flash, send_file, abort
)

from .settings import (
    SECRET_KEY, BRAND_NAME, ADMIN_EMAIL, ADMIN_PASSWORD,
    MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM, MAIL_USE_TLS,
    REPORT_VALIDITY_DAYS, LOG_LEVEL, RUN_DB_INIT, GOOGLE_PSI_API_KEY
)
from .models import (
    init_engine, create_schema, get_db,
    User, Site, Audit, Schedule, VerificationToken
)
from .metrics import run_full_audit, save_overall_chart, save_categories_chart

import logging
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger("fftech-main")

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = SECRET_KEY

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
CHARTS_DIR = os.path.join(STATIC_DIR, 'charts')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CHARTS_DIR, exist_ok=True)

# DB boot
init_engine()
if RUN_DB_INIT:
    create_schema()

# ---------- helpers ----------
def render_safe(tpl: str, **ctx):
    try: return render_template(tpl, **ctx)
    except Exception:
        return render_template_string("<html><body><pre>{{ ctx|tojson }}</pre></body></html>", ctx=ctx)

def normalize_url(raw: str) -> str:
    raw = (raw or '').strip()
    if not raw: return raw
    from urllib.parse import urlparse
    p = urlparse(raw)
    if not p.scheme: raw = 'https://' + raw
    return raw

def send_verification_email(to_email: str, verify_link: str, name: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"{BRAND_NAME} – Verify your email"
    msg["From"] = MAIL_FROM
    msg["To"] = to_email
    # FIXED: Using triple quotes to allow multi-line email body
    msg.set_content(f"""Hello {name},

Please verify your email:
{verify_link}

Regards,
{BRAND_NAME}""")
    try:
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as s:
            if MAIL_USE_TLS: s.starttls()
            if MAIL_USERNAME and MAIL_PASSWORD: s.login(MAIL_USERNAME, MAIL_PASSWORD)
            s.send_message(msg)
    except Exception as ex:
        log.warning("Email send failed: %s", ex)

# ---------- routes ----------
@app.get('/healthz')
def healthz(): return {"status":"ok"}, 200

@app.route('/')
def landing(): return render_safe('landing.html', title='Landing', BRAND_NAME=BRAND_NAME)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email'); name = request.form.get('name'); company = request.form.get('company')
        s = get_db()
        if s:
            try:
                if s.query(User).filter_by(email=email).first():
                    flash('Email already registered', 'error'); return redirect(url_for('register'))
                u = User(email=email, name=name, company=company, role='user', password_hash='', verified=False)
                s.add(u); s.commit()
                token = f"verify-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{email}"
                vt = VerificationToken(token=token, email=email, expires_at=datetime.utcnow()+timedelta(hours=24))
                s.add(vt); s.commit()
                verify_link = url_for('verify', token=token, _external=True)
                send_verification_email(email, verify_link, name or "")
                return render_safe('register_done.html', email=email, verify_link=verify_link, BRAND_NAME=BRAND_NAME)
            except Exception as ex:
                s.rollback(); flash(f'DB error: {ex}', 'error')
    return render_safe('register.html', BRAND_NAME=BRAND_NAME)

@app.route('/verify')
def verify():
    token = request.args.get('token')
    s = get_db()
    if s and token:
        vt = s.query(VerificationToken).filter_by(token=token).first()
        if vt and vt.expires_at >= datetime.utcnow():
            return render_safe('set_password.html', token=token, email=vt.email, BRAND_NAME=BRAND_NAME)
    abort(400)

@app.route('/set_password', methods=['POST'])
def set_password():
    token = request.form.get('token'); password = request.form.get('password')
    s = get_db()
    if s and token:
        vt = s.query(VerificationToken).filter_by(token=token).first()
        if vt and vt.expires_at >= datetime.utcnow():
            try:
                u = s.query(User).filter_by(email=vt.email).first()
                if u:
                    from werkzeug.security import generate_password_hash
                    u.verified = True; u.password_hash = generate_password_hash(password)
                    s.query(VerificationToken).filter_by(token=token).delete()
                    s.commit()
                    flash('Password set. You can now log in.', 'success')
                    return render_safe('verify_success.html', BRAND_NAME=BRAND_NAME)
            except Exception as ex:
                s.rollback(); flash(f'DB error: {ex}', 'error')
    abort(400)

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email'); password = request.form.get('password')
        s = get_db()
        if s:
            try:
                from werkzeug.security import check_password_hash
                u = s.query(User).filter_by(email=email).first()
                if u and u.verified and check_password_hash(u.password_hash or '', password or ''):
                    session['user'] = u.email; session['role'] = u.role
                    flash('Logged in successfully','success')
                    return redirect(url_for('results_page'))
            except Exception:
                pass
        flash('Invalid credentials or unverified email','error')
    return render_safe('login.html', BRAND_NAME=BRAND_NAME)

@app.route('/logout')
def logout():
    session.clear(); flash('Logged out','success'); return redirect(url_for('landing'))

@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email') or ''; password = request.form.get('password') or ''
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session['user'] = ADMIN_EMAIL; session['role'] = 'admin'
            flash('Admin logged in successfully','success'); return redirect(url_for('dashboard'))
        flash('Invalid admin credentials','error')
    return render_safe('login.html', BRAND_NAME=BRAND_NAME)

@app.route('/admin/dashboard')
def dashboard():
    if session.get('role') != 'admin':
        return {'detail':'Admin only'}, 403
    s = get_db(); stats = {}; users_fmt = []
    if s:
        try:
            users = s.query(User).all(); audits = s.query(Audit).all()
            stats = {'users': len(users), 'audits': len(audits)}
            users_fmt = [{'email': u.email, 'role': u.role, 'name': u.name, 'company': u.company} for u in users]
        except Exception:
            pass
    return render_safe('admin_dashboard.html', stats=stats, users=users_fmt, BRAND_NAME=BRAND_NAME)

@app.route('/sites/add', methods=['POST'])
def add_site():
    if not session.get('user'): return redirect(url_for('login'))
    url = normalize_url(request.form.get('url'))
    s = get_db()
    if s and url:
        try:
            site = s.query(Site).filter_by(owner_email=session['user'], url=url).first()
            if not site:
                site = Site(owner_email=session['user'], url=url); s.add(site); s.commit()
            flash('Site added','success')
        except Exception as ex:
            s.rollback(); flash(f'DB error: {ex}', 'error')
    return redirect(url_for('results_page', url=url))

@app.route('/schedule', methods=['GET','POST'])
def schedule():
    if not session.get('user'): return redirect(url_for('login'))
    s = get_db()
    if request.method == 'POST':
        site_url = normalize_url(request.form.get('url'))
        cron_time = request.form.get('cron') or '06:00'
        typ = request.form.get('type') or 'daily'
        if s:
            try:
                site = s.query(Site).filter_by(owner_email=session['user'], url=site_url).first()
                if not site: site = Site(owner_email=session['user'], url=site_url); s.add(site); s.commit()
                sc = Schedule(user_email=session['user'], site_id=site.id, cron_time=cron_time, type=typ, active=True)
                s.add(sc); s.commit(); flash('Schedule created','success')
            except Exception as ex:
                s.rollback(); flash(f'DB error: {ex}', 'error')
    return render_safe('schedule.html', BRAND_NAME=BRAND_NAME)

@app.route('/results')
def results_page():
    if not session.get('user'): return redirect(url_for('login'))
    url = normalize_url(request.args.get('url','https://example.com'))
    s = get_db()
    if s:
        u = s.query(User).filter_by(email=session['user']).first()
        if u and not u.subscribed and u.audits_remaining <= 0:
            flash('Free audits exhausted. Please subscribe ($5/month) to continue.', 'error')
            return redirect(url_for('landing'))
    try:
        categories_100, details = run_full_audit(url, psi_key=GOOGLE_PSI_API_KEY)
    except Exception as ex:
        flash(f'Audit failed: {ex}', 'error'); return redirect(url_for('landing'))

    def weighted_overall_10(cat):
        DEFAULT = 75.0
        weights = {"Performance & Web Vitals":0.28,"Accessibility":0.12,"Best Practices":0.12,
                   "SEO":0.18,"Crawlability & Indexation":0.10,"URL & Internal Linking":0.06,
                   "Security & HTTPS":0.10,"Mobile & Usability":0.04}
        total = sum(float(cat.get(k, DEFAULT))*w for k, w in weights.items())
        return round((total / max(sum(weights.values()), 1e-9))/10.0, 2)
    def grade_from_score(score10):
        return "A+" if score10>=9.5 else "A" if score10>=8.5 else "B" if score10>=7.0 else "C" if score10>=5.5 else "D"

    overall10 = weighted_overall_10(categories_100); grade = grade_from_score(overall10)

    if s:
        try:
            site = s.query(Site).filter_by(owner_email=session['user'], url=url).first()
            if not site: site = Site(owner_email=session['user'], url=url); s.add(site); s.commit()
            summary = f"Overall {overall10:.2f}/10 ({grade}). Improve Performance, SEO, and Security."
            a = Audit(user_email=session['user'], site_id=site.id, url=url,
                      grade=grade, summary=summary, overall_score=int(round(overall10*10)),
                      metrics_json=json.dumps(details, ensure_ascii=False))
            s.add(a)
            u = s.query(User).filter_by(email=session['user']).first()
            if u and not u.subscribed and u.audits_remaining > 0:
                u.audits_remaining -= 1
            s.commit()
        except Exception as ex:
            s.rollback(); flash(f'DB error: {ex}', 'error')

    save_overall_chart(overall10, os.path.join(CHARTS_DIR, "overall_gauge.png"))
    save_categories_chart(categories_100, os.path.join(CHARTS_DIR, "category_scores.png"))

    results = {
        "site_health": {"score": overall10, "grade": grade,
                         "errors": details["overall_site_health"]["total_errors"],
                         "warnings": details["overall_site_health"]["total_warnings"],
                         "notices": details["overall_site_health"]["total_notices"]},
        "summary": f"Audit completed: Overall {overall10:.2f}/10 ({grade}).",
        "charts": {"overall_gauge": f"/static/charts/overall_gauge.png",
                    "category_bar": f"/static/charts/category_scores.png",
                    "issues_donut": f"/static/charts/category_scores.png"},
        "categories_100": categories_100,
        "details": details
    }

    return render_safe('results.html', title='Registered Audit', url=url,
                       date=datetime.utcnow().strftime("%Y-%m-%d"),
                       results=results, mode='registered', BRAND_NAME=BRAND_NAME)

@app.route('/history')
def history():
    if not session.get('user'): return redirect(url_for('login'))
    s = get_db(); audits = []
    if s:
        try:
            rows = s.query(Audit).filter_by(user_email=session['user']).all()
            audits = [{"date": r.date, "url": r.url, "grade": r.grade, "overall_score": r.overall_score} for r in rows]
        except Exception: pass
    return render_safe('audit_history.html', audits=audits, BRAND_NAME=BRAND_NAME)

@app.route('/subscribe', methods=['POST'])
def subscribe():
    if not session.get('user'): return redirect(url_for('login'))
    s = get_db()
    if s:
        try:
            u = s.query(User).filter_by(email=session['user']).first()
            if u:
                u.subscribed = True; u.audits_remaining = 99999
                s.commit(); flash('Subscription activated. Thank you!', 'success')
        except Exception as ex:
            s.rollback(); flash(f'DB error: {ex}', 'error')
    return redirect(url_for('results_page'))

@app.route('/report.pdf')
def report_pdf():
    if not session.get('user'): return redirect(url_for('login'))
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    url = request.args.get('url','https://example.com')
    path = os.path.join(DATA_DIR, 'report.pdf')
    c = canvas.Canvas(path, pagesize=A4); width, height = A4

    categories_100, _ = run_full_audit(url, psi_key=GOOGLE_PSI_API_KEY)
    def weighted_overall_10(cat):
        DEFAULT = 75.0
        weights = {"Performance & Web Vitals":0.28,"Accessibility":0.12,"Best Practices":0.12,
                   "SEO":0.18,"Crawlability & Indexation":0.10,"URL & Internal Linking":0.06,
                   "Security & HTTPS":0.10,"Mobile & Usability":0.04}
        total = sum(float(cat.get(k, DEFAULT))*w for k, w in weights.items())
        return round((total / max(sum(weights.values()), 1e-9))/10.0, 2)
    overall10 = weighted_overall_10(categories_100)
    grade = "A+" if overall10>=9.5 else "A" if overall10>=8.5 else "B" if overall10>=7.0 else "C" if overall10>=5.5 else "D"

    c.setFillColorRGB(0, 0.64, 1); c.rect(40, height-80, 360, 30, fill=1)
    c.setFillColorRGB(1,1,1); c.drawString(50, height-65, f'{BRAND_NAME} – Certified Audit')
    c.setFillColorRGB(0.1,0.1,0.1)
    c.drawString(40, height-110, f'URL: {url}')
    c.drawString(40, height-130, f'Date: {datetime.utcnow().strftime("%Y-%m-%d")}')
    c.drawString(40, height-150, f'Overall Grade: {grade}')
    c.drawString(40, height-170, f'Overall Score: {overall10:.2f} / 10')
    valid_until = datetime.utcnow() + timedelta(days=REPORT_VALIDITY_DAYS)
    c.drawString(40, height-190, f'Valid Until: {valid_until.strftime("%Y-%m-%d")}')
    c.setFillColorRGB(0, 0.64, 1); c.circle(width-80, 80, 30, fill=1)
    c.setFillColorRGB(1,1,1); c.drawString(width-105, 80, 'FF Tech')
    c.showPage(); c.save()
    return send_file(path, mimetype='application/pdf', as_attachment=True, download_name='FFTech_Audit_Report.pdf')

@app.route('/cron/daily')
def cron_daily():
    now = datetime.utcnow().strftime("%H:%M")
    s = get_db()
    if not s: return {"detail":"DB not available"}, 500
    sent = 0
    try:
        scs = s.query(Schedule).filter_by(type="daily", active=True).all()
        for sc in scs:
            if sc.cron_time == now:
                site = s.query(Site).filter_by(id=sc.site_id).first()
                if site:
                    cats, _ = run_full_audit(site.url, psi_key=GOOGLE_PSI_API_KEY)
                    overall10 = sum(cats.values())/max(len(cats),1)/10.0
                    grade = "A+" if overall10>=9.5 else "A" if overall10>=8.5 else "B" if overall10>=7 else "C" if overall10>=5.5 else "D"
                    msg = EmailMessage()
                    msg["Subject"] = f"{BRAND_NAME} – Daily Audit ({site.url})"
                    msg["From"] = MAIL_FROM; msg["To"] = sc.user_email
                    # FIXED: Added triple quotes for multi-line content
                    msg.set_content(f"""Daily audit for {site.url}:
Overall {overall10:.2f}/10 ({grade}).""")
                    with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as smtp:
                        if MAIL_USE_TLS: smtp.starttls()
                        if MAIL_USERNAME and MAIL_PASSWORD: smtp.login(MAIL_USERNAME, MAIL_PASSWORD)
                        smtp.send_message(msg); sent += 1
        return {"sent": sent}, 200
    except Exception as ex:
        return {"error": str(ex)}, 500

@app.route('/cron/accumulated')
def cron_accumulated():
    return {"detail":"Accumulated report stub"}, 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT','8000')))
