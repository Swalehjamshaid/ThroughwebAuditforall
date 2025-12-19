import os
import time
import datetime
import requests
import urllib3
from bs4 import BeautifulSoup
from fpdf import FPDF
from fastapi import FastAPI, HTTPException, Depends, Response, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Suppress SSL warnings for bypassed sites
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Database Setup
DB_URL = os.getenv('DATABASE_URL', 'sqlite:///./test.db')
if DB_URL.startswith('postgres://'):
    DB_URL = DB_URL.replace('postgres://', 'postgresql://', 1)

engine = create_engine(DB_URL, connect_args={'check_same_thread': False} if 'sqlite' in DB_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AuditRecord(Base):
    __tablename__ = 'audit_reports'
    id = Column(Integer, primary_key=True)
    url = Column(String)
    grade = Column(String)
    score = Column(Integer)
    metrics = Column(JSON)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)
app = FastAPI()
templates = Jinja2Templates(directory='templates')

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- THE 45+ METRIC AUDIT ENGINE ---
def run_audit(url: str):
    if not url.startswith('http'): url = 'https://' + url
    h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}
    
    try:
        start = time.time()
        # verify=False fixes the SSL/Certificate errors seen in your logs
        res = requests.get(url, headers=h, timeout=25, verify=False)
        soup = BeautifulSoup(res.text, 'html.parser')
        m = {}

        # 1. SEO & CONTENT (15 Metrics)
        m['Title Tag'] = soup.title.string.strip()[:60] if soup.title else 'Missing'
        m['Title Length'] = len(m['Title Tag'])
        m['H1 Count'] = len(soup.find_all('h1'))
        m['H2 Count'] = len(soup.find_all('h2'))
        m['H3 Count'] = len(soup.find_all('h3'))
        m['H4 Count'] = len(soup.find_all('h4'))
        m['Meta Description'] = 'Present' if soup.find('meta', attrs={'name': 'description'}) else 'Missing'
        m['Total Images'] = len(soup.find_all('img'))
        m['Images Without Alt'] = len([i for i in soup.find_all('img') if not i.get('alt')])
        m['Total Links'] = len(soup.find_all('a'))
        m['Internal Links'] = len([a for a in soup.find_all('a', href=True) if a['href'].startswith('/')])
        m['External Links'] = len([a for a in soup.find_all('a', href=True) if 'http' in a['href']])
        m['Word Count'] = len(soup.get_text().split())
        m['Canonical Tag'] = 'Found' if soup.find('link', rel='canonical') else 'Missing'
        m['Favicon'] = 'Found' if soup.find('link', rel='icon') else 'Missing'

        # 2. TECHNICAL & SECURITY (15 Metrics)
        m['SSL Active'] = 'Yes' if url.startswith('https') else 'No'
        m['Page Load Time'] = f"{round(time.time()-start, 2)}s"
        m['Page Size'] = f"{round(len(res.content)/1024, 2)} KB"
        m['Server Software'] = res.headers.get('Server', 'Private')
        m['Viewport Config'] = 'Yes' if soup.find('meta', name='viewport') else 'No'
        m['CharSet'] = 'UTF-8' if soup.find('meta', charset=True) else 'Not Defined'
        m['Script Tags'] = len(soup.find_all('script'))
        m['Stylesheet Links'] = len(soup.find_all('link', rel='stylesheet'))
        m['Inline Styles'] = len(soup.find_all('style'))
        m['Forms Found'] = len(soup.find_all('form'))
        m['iFrames'] = len(soup.find_all('iframe'))
        m['Tables'] = len(soup.find_all('table'))
        m['Compression'] = res.headers.get('Content-Encoding', 'None')
        m['X-Frame-Options'] = res.headers.get('X-Frame-Options', 'Not Set')
        m['Language Code'] = soup.html.get('lang', 'Not Set') if soup.html else 'Missing'

        # 3. SOCIAL & ADVANCED (15+ Metrics)
        m['OG Title'] = 'Present' if soup.find('meta', property='og:title') else 'Missing'
        m['OG Image'] = 'Present' if soup.find('meta', property['og:image']) else 'Missing'
        m['Twitter Card'] = 'Present' if soup.find('meta', name='twitter:card') else 'Missing'
        m['JSON-LD Schema'] = 'Found' if soup.find('script', type='application/ld+json') else 'Missing'
        m['SVG Icons'] = len(soup.find_all('svg'))
        m['Input Fields'] = len(soup.find_all('input'))
        m['Button Elements'] = len(soup.find_all('button'))
        m['Navigation Blocks'] = len(soup.find_all('nav'))
        m['Footer Section'] = 'Found' if soup.find('footer') else 'Missing'
        m['Video Tags'] = len(soup.find_all('video'))
        m['Audio Tags'] = len(soup.find_all('audio'))
        m['Bold Elements'] = len(soup.find_all(['b', 'strong']))
        m['List Elements'] = len(soup.find_all(['ul', 'ol']))
        m['Meta Robots'] = 'Found' if soup.find('meta', name='robots') else 'Missing'
        
        # Fragmented string fix for HTML comments to prevent SyntaxError
        lt = '<'
        comment = lt + '!--'
        m['Code Comments'] = 'Yes' if comment in res.text else 'No'

        # Scoring Logic
        score = min(100, (m['H1 Count'] > 0)*15 + (url.startswith('https'))*25 + (m['Viewport Config'] == 'Yes')*10 + 50)
        grade = 'A' if score >= 85 else 'B' if score >= 70 else 'C'
        
        return {'url': url, 'grade': grade, 'score': score, 'metrics': m}
    except Exception as e:
        print(f"Detailed Error: {e}")
        return None

# --- ROUTES ---
@app.get('/')
def home(request: Request):
    return templates.TemplateResponse('index.html', {'request': request})

@app.post('/audit')
def do_audit(data: dict, db: Session = Depends(get_db)):
    res = run_audit(data.get('url'))
    if not res: 
        raise HTTPException(400, "The audit failed. Site may be blocking the scanner or SSL is invalid.")
    
    report = AuditRecord(**res)
    db.add(report)
    db.commit()
    db.refresh(report)
    return {'id': report.id, 'data': res}

@app.get('/download/{report_id}')
def download(report_id: int, db: Session = Depends(get_db)):
    report = db.query(AuditRecord).filter(AuditRecord.id == report_id).first()
    if not report: raise HTTPException(404)
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, f"Full Audit Report: {report.url}", ln=1, align='C')
    pdf.set_font('Arial', size=10)
    pdf.ln(10)
    
    for k, v in report.metrics.items():
        pdf.cell(0, 8, txt=f"{k}: {v}", ln=1)
        
    return Response(content=pdf.output(dest='S').encode('latin-1'), media_type='application/pdf')

# RAILWAY PORT BINDING
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
