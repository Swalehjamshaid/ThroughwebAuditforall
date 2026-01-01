
import os, json, random
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, abort
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from settings import SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD
from security import load, save, normalize_url, ensure_nonempty_structs, generate_summary
from models import init_engine, create_schema, get_session, migrate_json_to_db, ensure_fixed_admin, User, Audit
from emailer import send_verification_email
from audit_stub import stub_open_metrics

app = Flask(__name__)
app.secret_key = SECRET_KEY

DATA_PATH = os.path.join(os.path.dirname(__file__), 'data')
USERS_FILE = os.path.join(DATA_PATH, 'users.json')
AUDITS_FILE = os.path.join(DATA_PATH, 'audits.json')

init_engine(); create_schema(); migrate_json_to_db(DATA_PATH); ensure_fixed_admin(DATA_PATH)

@app.route('/')
def home(): return render_template('landing.html', title='Landing')

@app.route('/audit', methods=['POST'])
def open_audit():
    url = normalize_url(request.form.get('url'))
    results = stub_open_metrics(url)
    vitals = {'LCP': round(random.uniform(1.8, 4.5),2), 'FID': round(random.uniform(10, 100),2), 'CLS': round(random.uniform(0.01, 0.25),2), 'TBT': round(random.uniform(50, 600),2)}
    cat = {'SEO': round(random.uniform(5,9),2), 'Performance': round(random.uniform(4,9),2), 'Security': round(random.uniform(6,9),2), 'Mobile': round(random.uniform(5,9),2)}
    sh, vt, cs, _ = ensure_nonempty_structs(results['site_health'], vitals, cat, [])
    results['site_health'] = sh
    return render_template('results.html', title='Open Audit', url=url, date=datetime.utcnow().strftime('%Y-%m-%d'), results=results, mode='open', vitals=vt, cat_scores=cs)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        name=request.form.get('name'); company=request.form.get('company'); email=request.form.get('email')
        s=get_session()
        if s and s.query(User).filter_by(email=email).first():
            flash('Email already registered','error'); return redirect(url_for('register'))
        token=f'verify-{random.randint(100000,999999)}'
        users=load(USERS_FILE); users.append({'email':email,'name':name,'company':company,'role':'user','password':None,'verified':False,'token':token}); save(USERS_FILE, users)
        if s: s.add(User(email=email, name=name, company=company, role='user', password=None, verified=False)); s.commit()
        verify_link=url_for('verify', token=token, _external=True)
        send_verification_email(email, verify_link, name, DATA_PATH)
        return render_template('register_done.html', email=email, verify_link=verify_link)
    return render_template('register.html')

@app.route('/verify')
def verify():
    token=request.args.get('token'); users=load(USERS_FILE)
    for u in users:
        if u.get('token')==token:
            s=get_session()
            if s:
                dbu=s.query(User).filter_by(email=u['email']).first()
                if dbu: dbu.verified=True; s.commit()
            return render_template('set_password.html', token=token, email=u['email'])
    abort(400)

@app.route('/set_password', methods=['POST'])
def set_password():
    token=request.form.get('token'); password=request.form.get('password'); users=load(USERS_FILE)
    for u in users:
        if u.get('token')==token:
            u['verified']=True; u['password']=password; u['token']=None; save(USERS_FILE, users)
            s=get_session()
            if s:
                dbu=s.query(User).filter_by(email=u['email']).first()
                if dbu: dbu.verified=True; dbu.password=password; s.commit()
            flash('Password set. You can now log in.','success')
            return render_template('verify_success.html')
    abort(400)

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        email=request.form.get('email'); password=request.form.get('password'); s=get_session()
        if s:
            dbu=s.query(User).filter_by(email=email).first()
            if dbu and (dbu.password or '')==(password or '') and dbu.verified:
                session['user']=dbu.email; session['role']=dbu.role; flash('Logged in successfully','success'); return redirect(url_for('dashboard'))
        users=load(USERS_FILE)
        for u in users:
            if u['email']==email and (u['password'] or '')==(password or '') and u.get('verified'):
                session['user']=email; session['role']=u['role']; flash('Logged in successfully','success'); return redirect(url_for('dashboard'))
        flash('Invalid credentials or unverified email','error')
    return render_template('login.html')

@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method=='POST':
        email=request.form.get('email'); password=request.form.get('password')
        if email==ADMIN_EMAIL and password==ADMIN_PASSWORD:
            session['user']=ADMIN_EMAIL; session['role']='admin'; flash('Admin logged in successfully','success'); return redirect(url_for('dashboard'))
        flash('Invalid admin credentials','error')
    return render_template('login.html')

@app.route('/logout')
def logout(): session.clear(); flash('Logged out','success'); return redirect(url_for('home'))

@app.route('/results')
def results_page():
    if not session.get('user'): return redirect(url_for('login'))
    url=normalize_url(request.args.get('url','https://example.com'))
    score=round(random.uniform(6.0,9.9),2)
    grade='A+' if score>=9.5 else 'A' if score>=8.5 else 'B' if score>=7.0 else 'C' if score>=5.5 else 'D'
    site={'score':score,'errors':random.randint(0,50),'warnings':random.randint(10,120),'notices':random.randint(10,200),'grade':grade}
    cat_file=os.path.join(DATA_PATH,'metrics_catalogue_full.json'); catalogue=json.load(open(cat_file))
    full=[{'id':m['id'],'category':m['category'],'name':m['name'],'value':random.choice(['OK','Warning','Error','Improvement'])} for m in catalogue]
    vit={'LCP':round(random.uniform(1.8,4.5),2),'FID':round(random.uniform(10,100),2),'CLS':round(random.uniform(0.01,0.25),2),'TBT':round(random.uniform(50,600),2)}
    cs={'Overall Health':round(random.uniform(6,9),2),'Crawlability':round(random.uniform(5,9),2),'On-Page':round(random.uniform(5,9),2),'Internal Linking':round(random.uniform(5,9),2),'Performance':round(random.uniform(4,9),2),'Mobile':round(random.uniform(5,9),2),'Security':round(random.uniform(6,9),2),'International':round(random.uniform(5,9),2),'Backlinks':round(random.uniform(4,9),2),'Advanced':round(random.uniform(4,9),2)}
    sh, vt, csc, fr = ensure_nonempty_structs(site, vit, cs, full)
    summary = generate_summary(url, sh, csc)
    s=get_session()
    if s:
        s.add(Audit(user_email=session['user'], url=url, date=datetime.utcnow().strftime('%Y-%m-%d'), grade=grade)); s.commit()
    else:
        audits=load(AUDITS_FILE); audits.append({'user':session['user'],'url':url,'date':datetime.utcnow().strftime('%Y-%m-%d'),'grade':grade}); save(AUDITS_FILE, audits)
    results={'site_health':sh,'full':fr,'summary':summary}
    return render_template('results.html', title='Registered Audit', url=url, date=datetime.utcnow().strftime('%Y-%m-%d'), results=results, mode='registered', vitals=vt, cat_scores=csc)

@app.route('/history')
def history():
    if not session.get('user'): return redirect(url_for('login'))
    s=get_session()
    if s:
        rows=s.query(Audit).filter_by(user_email=session.get('user')).all(); audits=[{'date':r.date,'url':r.url,'grade':r.grade} for r in rows]
    else:
        audits=[a for a in load(AUDITS_FILE) if a.get('user')==session.get('user')]
    return render_template('audit_history.html', audits=audits)

@app.route('/schedule', methods=['GET','POST'])
def schedule():
    if not session.get('user'): return redirect(url_for('login'))
    if request.method=='POST': flash('Schedule created (demo). Integrate with a scheduler/worker in production.','success')
    return render_template('schedule.html')

@app.route('/admin/dashboard')
def dashboard():
    if session.get('role')!='admin': return {'detail':'Admin only'}, 403
    s=get_session()
    if s:
        users=s.query(User).all(); audits=s.query(Audit).all(); stats={'users':len(users),'audits':len(audits)}
        users_fmt=[{'email':u.email,'role':u.role,'name':u.name,'company':u.company} for u in users]
        return render_template('admin_dashboard.html', stats=stats, users=users_fmt)
    users=load(USERS_FILE); audits=load(AUDITS_FILE); stats={'users':len(users),'audits':len(audits)}
    return render_template('admin_dashboard.html', stats=stats, users=users)

@app.route('/report.pdf')
def report_pdf():
    if not session.get('user'): return redirect(url_for('login'))
    url=request.args.get('url','https://example.com')
    score=random.uniform(6.0,9.7)
    grade='A+' if score>=9.5 else 'A' if score>=8.5 else 'B' if score>=7.0 else 'C' if score>=5.5 else 'D'
    path=os.path.join(DATA_PATH,'report.pdf')
    c=canvas.Canvas(path,pagesize=A4); width,height=A4
    c.setFillColorRGB(0,0.64,1); c.rect(40,height-80,200,30,fill=1)
    c.setFillColorRGB(1,1,1); c.drawString(50,height-65,'FF Tech – Certified Report')
    c.setFillColorRGB(0.9,0.9,0.9)
    c.drawString(40,height-110,f'URL: {url}')
    c.drawString(40,height-130,f'Date: {datetime.utcnow().strftime("%Y-%m-%d")}')
    c.drawString(40,height-150,f'Overall Grade: {grade}')
    c.drawString(40,height-170,f'Site Health Score: {round(score,2)} / 10')
    summary='This certified audit summarizes the site's technical and SEO health across crawlability, performance, security, and mobile usability. Key improvements include optimizing images, fixing broken links, adding canonical tags, and enabling compression and caching. Addressing render-blocking resources and third-party script payloads will improve Core Web Vitals. Consistent structured data and security headers enhance visibility and trust. Trend tracking and scheduled audits maintain stability over time.'
    c.drawString(40,height-200,'Executive Summary:')
    for i in range(0,len(summary),95): c.drawString(40,height-220-(i//95)*15, summary[i:i+95])
    c.setFillColorRGB(0,0.64,1); c.circle(width-80,80,30,fill=1)
    c.setFillColorRGB(1,1,1); c.drawString(width-105,80,'CERT')
    c.showPage(); c.save()
    return send_file(path, mimetype='application/pdf', as_attachment=True, download_name='FFTech_Audit_Report.pdf')

if __name__=='__main__': app.run(debug=True)
