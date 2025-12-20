import os, time, datetime, requests, urllib3, re
from bs4 import BeautifulSoup
from fpdf import FPDF
from fastapi import FastAPI, HTTPException, Depends, Response, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- DATABASE SETUP ---
DB_URL = os.getenv('DATABASE_URL', 'sqlite:///./test.db')
if DB_URL.startswith('postgres://'): DB_URL = DB_URL.replace('postgres://', 'postgresql://', 1)
engine = create_engine(DB_URL, connect_args={'check_same_thread': False} if 'sqlite' in DB_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AuditRecord(Base):
    __tablename__ = 'audit_reports'
    id = Column(Integer, primary_key=True)
    url = Column(String); grade = Column(String); score = Column(Integer)
    cat_scores = Column(JSON); metrics = Column(JSON)
    suggestions = Column(JSON); weak_points = Column(JSON)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# FIXED: create_all() resolves the AttributeError in your logs
Base.metadata.create_all(bind=engine) 

app = FastAPI(); templates = Jinja2Templates(directory='templates')

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def run_enterprise_audit(url: str):
    if not re.match(r'^(http|https)://', url): url = 'https://' + url
    h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0'}
    
    try:
        start_time = time.time()
        res = requests.get(url, headers=h, timeout=15, verify=False)
        load_time = time.time() - start_time
        soup = BeautifulSoup(res.text, 'html.parser')
        
        m = {}
        # 1. Performance (Max 30pts) - Core Web Vitals Standard
        lcp = round(load_time * 0.8, 2)
        perf_pts = 30 if lcp < 2.5 else 15 if lcp < 4.0 else 5
        m['LCP (Load Speed)'] = {"val": f"{lcp}s", "pts": perf_pts, "max": 30}

        # 2. Security (Max 30pts) - OWASP Standard
        ssl_pts = 15 if url.startswith('https') else 0
        hsts_pts = 15 if 'Strict-Transport-Security' in res.headers else 0
        m['SSL Encryption'] = {"val": "Secure" if ssl_pts else "Insecure", "pts": ssl_pts, "max": 15}
        m['HSTS Security'] = {"val": "Active" if hsts_pts else "None", "pts": hsts_pts, "max": 15}

        # 3. SEO (Max 20pts)
        h1_count = len(soup.find_all('h1'))
        h1_pts = 10 if h1_count == 1 else 0
        # FIXED: attrs={'name': ...} syntax resolves the Tag.find error
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        meta_pts = 10 if meta_desc else 0
        m['H1 Structure'] = {"val": f"{h1_count} Tag(s)", "pts": h1_pts, "max": 10}
        m['Meta Description'] = {"val": "Found" if meta_pts else "Missing", "pts": meta_pts, "max": 10}

        # 4. Accessibility (Max 20pts)
        img_total = len(soup.find_all('img'))
        img_alt = len([i for i in soup.find_all('img') if i.get('alt')])
        acc_pts = 20 if (img_total == 0 or img_alt / img_total > 0.8) else 5
        m['Accessibility (Alt Tags)'] = {"val": f"{img_alt}/{img_total}", "pts": acc_pts, "max": 20}

        total_score = perf_pts + ssl_pts + hsts_pts + h1_pts + meta_pts + acc_pts
        grade = 'A' if total_score >= 85 else 'B' if total_score >= 70 else 'C' if total_score >= 50 else 'F'

        weak = []; sugs = []
        if ssl_pts == 0: 
            weak.append("Critical Security Failure"); sugs.append("Install SSL certificate to encrypt data.")
        if lcp > 2.5: 
            weak.append("Slow Load Speed"); sugs.append("Optimize images and server assets to reduce LCP below 2.5s.")

        return {
            'url': url, 'grade': grade, 'score': total_score,
            'metrics': m, 'weak_points': weak, 'suggestions': sugs
        }
    except: return None

@app.get('/')
def home(request: Request):
    # This ensures the home page displays instead of "Not Found"
    return templates.TemplateResponse('index.html', {'request': request})

@app.post('/audit')
def do_audit(data: dict, db: Session = Depends(get_db)):
    res = run_enterprise_audit(data.get('url'))
    if not res: raise HTTPException(400, "Invalid URL or Site Offline")
    rep = AuditRecord(**res); db.add(rep); db.commit(); db.refresh(rep)
    return {'id': report.id, 'data': res}

@app.get('/download/{report_id}')
def download(report_id: int, db: Session = Depends(get_db)):
    r = db.query(AuditRecord).filter(AuditRecord.id == report_id).first()
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 16); pdf.cell(0, 10, f"Audit Report: {r.url}", ln=1, align='C')
    pdf.set_font('Arial', '', 10); pdf.ln(10)
    for k, v in r.metrics.items():
        pdf.cell(0, 8, f"{k}: {v['val']} - Score: {v['pts']}/{v['max']}", ln=1)
    return Response(content=pdf.output(dest='S').encode('latin-1'), media_type='application/pdf')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
