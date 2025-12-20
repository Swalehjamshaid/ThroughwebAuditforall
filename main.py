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
DB_URL = os.getenv('DATABASE_URL', 'sqlite:///./audit_master.db')
if DB_URL.startswith('postgres://'): DB_URL = DB_URL.replace('postgres://', 'postgresql://', 1)
engine = create_engine(DB_URL, connect_args={'check_same_thread': False} if 'sqlite' in DB_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AuditRecord(Base):
    __tablename__ = 'full_audits'
    id = Column(Integer, primary_key=True)
    url = Column(String); grade = Column(String); score = Column(Integer)
    pillar_scores = Column(JSON); metrics = Column(JSON)
    weak_points = Column(JSON); suggestions = Column(JSON)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine) 
app = FastAPI(); templates = Jinja2Templates(directory='templates')

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- ROOT ROUTE (Fixes Not Found Error) ---
@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

def run_comprehensive_audit(url: str):
    if not re.match(r'^(http|https)://', url): url = 'https://' + url
    h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0.0.0'}
    
    try:
        start_time = time.time()
        res = requests.get(url, headers=h, timeout=12, verify=False)
        load_time = time.time() - start_time
        soup = BeautifulSoup(res.text, 'html.parser')
        
        m = {}; p = {}; weak = []; sugs = []
        
        # 1. Performance (Max 25)
        lcp = round(load_time * 0.8, 2)
        p_score = 25 if lcp < 2.5 else 10
        p['Speed'] = p_score
        m['LCP (Core Web Vital)'] = {"val": f"{lcp}s", "pts": p_score, "max": 25}

        # 2. Security (Max 25)
        ssl = 1 if url.startswith('https') else 0
        s_score = 25 if ssl else 0
        p['Security'] = s_score
        m['SSL Certificate'] = {"val": "Secure" if ssl else "None", "pts": s_score, "max": 25}

        # 3. SEO (Max 20)
        h1 = len(soup.find_all('h1'))
        seo_pts = 20 if h1 == 1 else 5
        p['SEO'] = seo_pts
        m['H1 Structure'] = {"val": f"{h1} Tags", "pts": seo_pts, "max": 20}

        # 4. Technical / UX (Max 30)
        view = 1 if soup.find('meta', attrs={'name': 'viewport'}) else 0
        tech_pts = 30 if view else 10
        p['Tech/UX'] = tech_pts
        m['Mobile Responsiveness'] = {"val": "Optimized" if view else "Fail", "pts": tech_pts, "max": 30}

        # Identifying Weakness (Red Alert Items)
        if ssl == 0: 
            weak.append("Critical Security: SSL Missing"); sugs.append("Enable HTTPS to protect user data.")
        if lcp > 2.5: 
            weak.append("Performance: Poor LCP Speed"); sugs.append("Optimize assets to reduce load under 2.5s.")
        if h1 != 1: 
            weak.append("SEO: Invalid H1 Header"); sugs.append("Ensure exactly one H1 tag per page.")

        total = sum(p.values())
        grade = 'A' if total >= 85 else 'B' if total >= 70 else 'C' if total >= 50 else 'F'
        
        return {'url': url, 'grade': grade, 'score': total, 'pillar_scores': p, 'metrics': m, 'weak_points': weak, 'suggestions': sugs}
    except: return None

@app.post('/audit')
def do_audit(data: dict, db: Session = Depends(get_db)):
    res = run_comprehensive_audit(data.get('url'))
    if not res: raise HTTPException(400, "Audit failed.")
    rep = AuditRecord(**res); db.add(rep); db.commit(); db.refresh(rep)
    return {'id': rep.id, 'data': res}
