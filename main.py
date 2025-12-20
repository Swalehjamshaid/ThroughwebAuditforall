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
DB_URL = os.getenv('DATABASE_URL', 'sqlite:///./strict_audit.db')
engine = create_engine(DB_URL, connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AuditRecord(Base):
    __tablename__ = 'strict_audits'
    id = Column(Integer, primary_key=True)
    url = Column(String); grade = Column(String); score = Column(Integer)
    metrics = Column(JSON); weak_points = Column(JSON); suggestions = Column(JSON)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine) 
app = FastAPI(); templates = Jinja2Templates(directory='templates')

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- FIXED ROOT ROUTE ---
@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# --- THE STRICT AUDIT ENGINE ---
def run_strict_audit(url: str):
    if not re.match(r'^(http|https)://', url): url = 'https://' + url
    h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0.0.0'}
    
    try:
        start_time = time.time()
        res = requests.get(url, headers=h, timeout=15, verify=False)
        load_time = time.time() - start_time
        soup = BeautifulSoup(res.text, 'html.parser')
        
        m = {}; weak = []; sugs = []; points = 0

        # PILLAR 1: PERFORMANCE (LCP is 30% of score)
        lcp = round(load_time * 0.8, 2)
        perf_pts = 30 if lcp < 2.5 else 10 if lcp < 4 else 0
        m['Largest Contentful Paint (LCP)'] = {"val": f"{lcp}s", "pts": perf_pts, "max": 30}
        points += perf_pts
        if lcp > 2.5: 
            weak.append("Slow Load Time"); sugs.append("LCP exceeds 2.5s. Optimize images and server response.")

        # PILLAR 2: SECURITY (SSL is 30% of score)
        ssl = 1 if url.startswith('https') else 0
        sec_pts = 30 if ssl else 0
        m['SSL Certificate / HTTPS'] = {"val": "Active" if ssl else "MISSING", "pts": sec_pts, "max": 30}
        points += sec_pts
        if not ssl: 
            weak.append("Critical Security Gap"); sugs.append("Missing SSL. Browsers will mark site as 'Not Secure'.")

        # PILLAR 3: SEO STRUCTURE (20% of score)
        h1s = len(soup.find_all('h1'))
        seo_pts = 20 if h1s == 1 else 5
        m['SEO: H1 Tag Hierarchy'] = {"val": f"{h1s} Tags", "pts": seo_pts, "max": 20}
        points += seo_pts
        if h1s != 1: 
            weak.append("SEO Structural Failure"); sugs.append("Exactly one H1 tag is required for indexing.")

        # PILLAR 4: INFRASTRUCTURE (20% of score)
        view = 1 if soup.find('meta', attrs={'name': 'viewport'}) else 0
        m['Mobile Responsiveness'] = {"val": "Optimized" if view else "Fail", "pts": 20 if view else 0, "max": 20}
        points += m['Mobile Responsiveness']['pts']

        # THE STRICT LOGIC: Penalty Deductions
        final_score = points
        if not ssl: final_score = min(final_score, 40) # Auto-Fail if no SSL
        if lcp > 6: final_score = min(final_score, 30) # Auto-Fail if extremely slow

        grade = 'A' if final_score >= 85 else 'B' if final_score >= 70 else 'C' if final_score >= 50 else 'F'

        return {'url': url, 'grade': grade, 'score': final_score, 'metrics': m, 'weak_points': weak, 'suggestions': sugs}
    except: return None

@app.post('/audit')
def do_audit(data: dict, db: Session = Depends(get_db)):
    res = run_strict_audit(data.get('url'))
    if not res: raise HTTPException(400, "Scan Failed")
    rep = AuditRecord(**res); db.add(rep); db.commit(); db.refresh(rep)
    return {'id': rep.id, 'data': res}
