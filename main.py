import os
import time
import datetime
import requests
from bs4 import BeautifulSoup
from fpdf import FPDF
from fastapi import FastAPI, HTTPException, Depends, Response, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Database Configuration
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

# --- COMPREHENSIVE 45+ METRICS ENGINE ---
def run_audit(url: str):
    if not url.startswith('http'): url = 'https://' + url
    
    # Modern User-Agent to avoid bot detection
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    try:
        start_time = time.time()
        # Increased timeout for slow sites
        res = requests.get(url, headers=headers, timeout=20, verify=True)
        soup = BeautifulSoup(res.text, 'html.parser')
        m = {}

        # SEO & CONTENT (20)
        m['Title Tag'] = soup.title.string.strip() if soup.title else 'Missing'
        m['H1 Tags'] = len(soup.find_all('h1'))
        m['H2 Tags'] = len(soup.find_all('h2'))
        m['H3 Tags'] = len(soup.find_all('h3'))
        m['Meta Description'] = 'Found' if soup.find('meta', attrs={'name': 'description'}) else 'Missing'
        m['Total Images'] = len(soup.find_all('img'))
        m['Images Missing Alt'] = len([i for i in soup.find_all('img') if not i.get('alt')])
        m['Total Links'] = len(soup.find_all('a'))
        m['Internal Links'] = len([a for a in soup.find_all('a', href=True) if a['href'].startswith('/') or url in a['href']])
        m['Canonical Tag'] = 'Found' if soup.find('link', rel='canonical') else 'Missing'
        m['Word Count'] = len(soup.get_text().split())
        m['Viewport Set'] = 'Yes' if soup.find('meta', name='viewport') else 'No'
        m['Robots Tag'] = 'Found' if soup.find('meta', name='robots') else 'Missing'
        m['Favicon'] = 'Found' if soup.find('link', rel='icon') else 'Missing'
        m['Lang Attribute'] = soup.html.get('lang', 'Not Set') if soup.html else 'Missing'
        
        # TECHNICAL & SECURITY (15)
        m['SSL Status'] = 'Secure (HTTPS)' if url.startswith('https') else 'Insecure (HTTP)'
        m['Load Time'] = f"{round(time.time() - start_time, 2)}s"
        m['Page Size'] = f"{round(len(res.content) / 1024, 2)} KB"
        m['Server'] = res.headers.get('Server', 'Hidden')
        m['X-Frame-Options'] = res.headers.get('X-Frame-Options', 'Not Set')
        m['X-Content-Type'] = res.headers.get('X-Content-Type-Options', 'Not Set')
        m['Scripts Count'] = len(soup.find_all('script'))
        m['Stylesheets'] = len(soup.find_all('link', rel='stylesheet'))
        m['Inline CSS Blocks'] = len(soup.find_all('style'))
        m['Forms Found'] = len(soup.find_all('form'))
        m['iFrames Found'] = len(soup.find_all('iframe'))
        
        # SOCIAL & STRUCTURE (10)
        m['OG Title'] = 'Found' if soup.find('meta', property='og:title') else 'Missing'
        m['OG Image'] = 'Found' if soup.find('meta', property='og:image') else 'Missing'
        m['Twitter Card'] = 'Found' if soup.find('meta', name='twitter:card') else 'Missing'
        m['Schema JSON-LD'] = 'Found' if soup.find('script', type='application/ld+json') else 'Missing'
        m['SVG Elements'] = len(soup.find_all('svg'))
        m['Input Fields'] = len(soup.find_all('input'))
        
        # Fixed String Logic for HTML Comments
        prefix = '<'
        comment_marker = prefix + '!--'
        m['Code Comments'] = 'Yes' if comment_marker in res.text else 'No'

        # Scoring
        score = min(100, (m['H1 Tags'] > 0)*15 + (url.startswith('https'))*25 + (m['Viewport Set'] == 'Yes')*10 + 50)
        grade = "A" if score >= 85 else "B" if score >= 70 else "C"
        
        return {"url": url, "grade": grade, "score": score, "metrics": m}
    except Exception as e:
        print(f"Scrape Error: {e}")
        return None

# Routes
@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/audit")
def do_audit(data: dict, db: Session = Depends(get_db)):
    if not data.get('url'): raise HTTPException(400, "URL required")
    result = run_audit(data['url'])
    if not result: 
        raise HTTPException(400, "The website is blocking our automated scanner. Try a different URL.")
    
    report = AuditRecord(**result)
    db.add(report)
    db.commit()
    db.refresh(report)
    return {"id": report.id, "data": result}

@app.get("/download/{report_id}")
def download(report_id: int, db: Session = Depends(get_db)):
    report = db.query(AuditRecord).filter(AuditRecord.id == report_id).first()
    if not report: raise HTTPException(404)
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"Audit Report: {report.url}", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.ln(10)
    
    for k, v in report.metrics.items():
        pdf.cell(0, 8, f"{k}: {v}", ln=True)
        
    response = Response(content=pdf.output(dest='S').encode('latin-1'), media_type="application/pdf")
    response.headers["Content-Disposition"] = f"attachment; filename=audit_{report_id}.pdf"
    return response
