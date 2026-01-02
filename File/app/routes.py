# app/routes.py
from flask import render_template, request, redirect, url_for, flash, send_file
from app import app, db, mail
from app.models import User, Website, Audit
from flask_login import current_user, login_user, logout_user, login_required
from werkzeug.urls import url_parse
from flask_mail import Message
import uuid
import stripe
from app.tasks import perform_audit

stripe.api_key = app.config['STRIPE_SECRET_KEY']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email already registered')
            return redirect(url_for('register'))
        token = str(uuid.uuid4())
        user = User(email=email, verification_token=token)
        db.session.add(user)
        db.session.commit()
        msg = Message('Verify Your Email', sender=app.config['MAIL_USERNAME'], recipients=[email])
        msg.body = f'Click here to verify: {url_for("verify", token=token, _external=True)}'
        mail.send(msg)
        flash('Verification email sent')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/verify/<token>')
def verify(token):
    user = User.query.filter_by(verification_token=token).first()
    if user:
        user.verified = True
        user.verification_token = None
        db.session.commit()
        flash('Email verified. Set your password.')
        return redirect(url_for('set_password', user_id=user.id))
    flash('Invalid token')
    return redirect(url_for('register'))

@app.route('/set_password/<user_id>', methods=['GET', 'POST'])
def set_password(user_id):
    user = User.query.get(user_id)
    if not user or not user.verified:
        flash('Invalid request')
        return redirect(url_for('login'))
    if request.method == 'POST':
        password = request.form['password']
        user.set_password(password)
        db.session.commit()
        flash('Password set. Login now.')
        return redirect(url_for('login'))
    return render_template('set_password.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and user.verified and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            if not next_page or url_parse(next_page).netloc != '':
                next_page = url_for('dashboard')
            return redirect(next_page)
        flash('Invalid email or password')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    websites = current_user.websites.all()
    audits = current_user.audits.all()
    return render_template('dashboard.html', websites=websites, audits=audits)

@app.route('/add_website', methods=['GET', 'POST'])
@login_required
def add_website():
    if request.method == 'POST':
        url = request.form['url']
        schedule = request.form['schedule']
        website = Website(url=url, schedule=schedule, user_id=current_user.id)
        db.session.add(website)
        db.session.commit()
        tasks.schedule_audit(website.id, schedule)
        flash('Website added and scheduled')
        return redirect(url_for('dashboard'))
    return render_template('add_website.html')

@app.route('/audit/<int:website_id>')
@login_required
def run_audit(website_id):
    website = Website.query.get(website_id)
    if website.owner != current_user:
        flash('Unauthorized')
        return redirect(url_for('dashboard'))
    if current_user.audit_count >= app.config['AUDIT_FREE_LIMIT'] and not current_user.subscription_active:
        flash('Subscribe for more audits')
        return redirect(url_for('subscribe'))
    report = perform_audit(website.url)
    grade = 'A' if report['score'] > 90 else 'B'  # Simplify, use real grading
    audit = Audit(report=report, grade=grade, user_id=current_user.id, website_id=website.id)
    db.session.add(audit)
    db.session.commit()
    current_user.audit_count += 1
    db.session.commit()
    # Generate PDF (implement generate_pdf function)
    pdf_path = generate_pdf(report, grade)
    audit.pdf_path = pdf_path
    db.session.commit()
    return send_file(pdf_path, as_attachment=True)

@app.route('/subscribe', methods=['GET', 'POST'])
@login_required
def subscribe():
    if request.method == 'POST':
        token = request.form['stripeToken']
        customer = stripe.Customer.create(
            email=current_user.email,
            source=token
        )
        subscription = stripe.Subscription.create(
            customer=customer.id,
            items=[{'price': app.config['SUBSCRIPTION_PRICE_ID']}]
        )
        current_user.subscription_id = subscription.id
        current_user.subscription_active = True
        current_user.subscription_start = datetime.now()
        db.session.commit()
        flash('Subscribed successfully')
        return redirect(url_for('dashboard'))
    return render_template('subscribe.html', key=app.config['STRIPE_PUBLISHABLE_KEY'])

@app.route('/admin')
@login_required
def admin():
    if current_user.email != ADMIN_EMAIL:
        flash('Unauthorized')
        return redirect(url_for('dashboard'))
    users = User.query.all()
    return render_template('admin.html', users=users)

# Implement tasks.py for perform_audit and schedule_audit
# For perform_audit: Implement the 140+ metrics using libraries like requests, beautifulsoup, google PSI, etc.
# Example stub:
def perform_audit(url):
    # Implement metrics here
    return {'score': random.randint(70, 100), 'metrics': {}}

def generate_pdf(report, grade):
    # Implement PDF generation
    path = 'report.pdf'
    # Use reportlab as in original
    return path

def schedule_audit(website_id, schedule):
    # Use scheduler.add_job(perform_audit_task, 'cron', args=[website_id], hour=...) based on schedule
    pass
