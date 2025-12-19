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

# --- DATABASE ---
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

# --- 45+ METRICS ENGINE ---
def run_audit(url: str):
    if not url.startswith('http'): url = 'https://' + url
    h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}

    try:
        start = time.time()
        res = requests.get(url, headers=h, timeout=20, verify=True)
        soup = BeautifulSoup(res.text, 'html.parser')
        m = {}

        # 1. SEO & CONTENT (15 Metrics)
        m['Title'] = soup.title.string.strip()[:50] if soup.title else 'Missing'
        m['Title Length'] = len(m['Title'])
        m['H1 Tags'] = len(soup.find_all('h1'))
        m['H2 Tags'] = len(soup.find_all('h2'))
        m['H3 Tags'] = len(soup.find_all('h3'))
        m['Meta Description'] = 'Yes' if soup.find('meta', attrs={'name': 'description'}) else 'No'
        m['Images'] = len(soup.find_all('img'))
        m['Images Alt Missing'] = len([i for i in soup.find_all('img') if not i.get('alt')])
        m['Internal Links'] = len([a for a in soup.find_all('a', href=True) if a['href'].startswith('/')])
        m['External Links'] = len([a for a in soup.find_all('a', href=True) if a['href'].startswith('http')])
        m['Canonical Tag'] = 'Found' if soup.find('link', rel='canonical') else 'Missing'
        m['Viewport Meta'] = 'Yes' if soup.find('meta', name='viewport') else 'No'
        m['Robots Meta'] = 'Yes' if soup.find('meta', name='robots') else 'No'
        m['Word Count'] = len(soup.get_text().split())
        m['Favicon'] = 'Found' if soup.find('link', rel='icon') else 'Missing'

        # 2. SECURITY & PERFORMANCE (15 Metrics)
        m['SSL Active'] = 'Yes' if url.startswith('https') else 'No'
        m['Load Time'] = f"{round(time.time()-start, 2)}s"
        m['Page Size'] = f"{round(len(res.content)/1024, 2)} KB"
        m['Server'] = res.headers.get('Server', 'Hidden')
        m['Scripts'] = len(soup.find_all('script'))
        m['Stylesheets'] = len(soup.find_all('link', rel='stylesheet'))
        m['Inline CSS'] = len(soup.find_all('style'))
        m['Forms'] = len(soup.find_all('form'))
        m['iFrames'] = len(soup.find_all('iframe'))
        m['Tables'] = len(soup.find_all('table'))
        m['Compression'] = res.headers.get('Content-Encoding', 'None')
        m['CharSet'] = soup.find('meta', charset=True).get('charset') if soup.find('meta', charset=True) else 'Missing'
        
        # FIXED LINE: Prevent SyntaxError by splitting the string
        char_start = '<'
        comment_tag = char_start + '!--'
        m['HTML Comments'] = 'Found' if comment_tag in res.text else 'None'
        m['HSTS Header'] = 'Yes' if 'Strict-Transport-Security' in res.headers else 'No'
        m['X-Frame-Options'] = res.headers.get('X-Frame-Options', 'Not Set')

        # 3. SOCIAL & STRUCTURE (15 Metrics)
        m['OG Title'] = 'Yes' if soup.find('meta', property='og:title') else 'No'
        m['OG Image'] = 'Yes' if soup.find('meta', property='og:image') else 'No'
        m['Twitter Card'] = 'Yes' if soup.find('meta', name='twitter:card') else 'No'
        m['JSON-LD Schema'] = 'Found' if soup.find('script', type='application/ld+json') else 'Missing'
        m['Video Elements'] = len(soup.find_all('video'))
        m['Audio Elements'] = len(soup.find_all('audio'))
        m['SVG Graphics'] = len(soup.find_all('svg'))
        m['Input Fields'] = len(soup.find_all('input'))
        m['Buttons'] = len(soup.find_all('button'))
        m['Navigation Tags'] = len(soup.find_all('nav'))
        m['Footer Found'] = 'Yes' if soup.find('footer') else 'No'
        m['Language Attr'] = soup.html.get('lang', 'Missing') if soup.html else 'Missing'
        m['Head Section'] = 'Valid' if soup.head else 'Invalid'
        m['Body Section'] = 'Valid' if soup.body else 'Invalid'
        m['Copyright Info'] = 'Found' if '©' in soup.get_text() else 'Not Found'

        # Scoring logic
        score = min(100, (m['H1 Tags'] > 0)*10 + (url.startswith('https'))*20 + 50)
        grade = "A" if score >= 85 else "B" if score >= 70 else "C"
        
        return {"url": url, "grade": grade, "score": score, "metrics": m}
    except Exception as e:
        print(f"Error: {e}")
        return None

# --- PDF & ROUTES ---
@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/audit")
def do_audit(data: dict, db: Session = Depends(get_db)):
    res = run_audit(data.get('url'))
    if not res: raise HTTPException(400, "Audit Failed")
    report = AuditRecord(**res)
    db.add(report)
    db.commit()
    db.refresh(report)
    return {"id": report.id, "data": res}

@app.get("/download/{report_id}")
def download(report_id: int, db: Session = Depends(get_db)):
    report = db.query(AuditRecord).filter(AuditRecord.id == report_id).first()
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Throughweb Audit for {report.url}", ln=1, align='C')
    for k, v in report.metrics.items():
        pdf.cell(200, 10, txt=f"{k}: {v}", ln=1)
    return Response(content=pdf.output(dest='S').encode('latin-1'), media_type="application/pdf")
