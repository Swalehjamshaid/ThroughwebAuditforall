import os
import time
import datetime
import requests
import urllib3
import re
import random
from bs4 import BeautifulSoup
from fpdf import FPDF
from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from urllib.parse import quote_plus

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DB_URL = os.getenv('DATABASE_URL', 'sqlite:///./audits.db')
engine = create_engine(DB_URL, connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AuditRecord(Base):
    __tablename__ = 'reports'
    id = Column(Integer, primary_key=True)
    url = Column(String)
    grade = Column(String)
    score = Column(Integer)
    metrics = Column(JSON)
    broken_links = Column(JSON)
    financial_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Throughweb Elite Audit")
templates = Jinja2Templates(directory="templates")

class ElitePDF(FPDF):
    def header(self):
        self.set_fill_color(15, 23, 42)
        self.rect(0, 0, 210, 50, 'F')
        self.set_font('Helvetica', 'B', 24)
        self.set_text_color(255, 255, 255)
        self.cell(0, 30, 'ELITE WEBSITE AUDIT REPORT', 0, 1, 'C')

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

def run_live_audit(url: str):
    if not re.match(r'^https?://', url, re.I):
        url = 'https://' + url

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

    metrics = {}
    broken_links = []

    try:
        time.sleep(random.uniform(1.5, 3.5))
        start = time.time()
        res = requests.get(url, headers=headers, timeout=30, verify=False, allow_redirects=True)
        load_time = round(time.time() - start, 2)
        soup = BeautifulSoup(res.text, 'html.parser')
        final_url = res.url
        ssl = final_url.startswith('https')

        # PSI attempt
        psi_success = False
        try:
            time.sleep(random.uniform(1, 2))
            psi_res = requests.get(f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={quote_plus(final_url)}&strategy=desktop", timeout=15)
            if psi_res.ok:
                data = psi_res.json()
                if 'lighthouseResult' in data:
                    psi_success = True
                    lh = data['lighthouseResult']['audits']
                    metrics['Largest Contentful Paint (LCP)'] = {"val": lh['largest-contentful-paint']['displayValue'], "score": 100 if lh['largest-contentful-paint']['score'] >= 0.9 else 60, "status": "PASS" if lh['largest-contentful-paint']['score'] >= 0.9 else "WARN"}
        except:
            pass

        if not psi_success:
            est_lcp = round(load_time + 1.3, 2)
            metrics['Largest Contentful Paint (LCP)'] = {"val": f"{est_lcp}s (Est.)", "score": 100 if est_lcp < 2.5 else 70 if est_lcp < 4 else 40, "status": "PASS" if est_lcp < 2.5 else "WARN", "note": "Estimated from load time"}

        # Core custom checks
        title_len = len(soup.title.string.strip()) if soup.title and soup.title.string else 0
        metrics['Page Title'] = {"val": f"{title_len} chars", "score": 100 if 50 <= title_len <= 60 else 70 if title_len > 0 else 20, "status": "PASS" if 50 <= title_len <= 60 else "WARN"}

        viewport = bool(soup.find('meta', attrs={'name': 'viewport'}))
        metrics['Mobile Friendly'] = {"val": "Yes" if viewport else "No", "score": 100 if viewport else 30, "status": "PASS" if viewport else "FAIL"}

        metrics['HTTPS'] = {"val": "Secure" if ssl else "Insecure", "score": 100 if ssl else 0, "status": "PASS" if ssl else "FAIL"}

        # Broken links sample
        for a in soup.find_all('a', href=True)[:12]:
            if a['href'].startswith('/'):
                try:
                    full = requests.compat.urljoin(final_url, a['href'])
                    h = requests.head(full, headers=headers, timeout=6)
                    if h.status_code >= 400:
                        broken_links.append(full)
                except:
                    pass

        metrics['Broken Links'] = {"val": str(len(broken_links)), "score": 100 if len(broken_links) == 0 else 50 if len(broken_links) < 3 else 20, "status": "PASS" if len(broken_links) == 0 else "FAIL"}

        # Scoring
        scores = [v['score'] for v in metrics.values() if isinstance(v.get('score'), (int, float))]
        avg_score = round(sum(scores) / len(scores)) if scores else 60

        # Financial (realistic caps)
        leak = round(min((100 - avg_score) * 0.25 + len(broken_links) * 2, 40), 1)
        gain = round(leak * 1.4, 1)

        grade = 'A+' if avg_score >= 95 else 'A' if avg_score >= 85 else 'B' if avg_score >= 70 else 'C' if avg_score >= 50 else 'D'

        return {
            'url': final_url,
            'grade': grade,
            'score': avg_score,
            'metrics': metrics,
            'broken_links': broken_links,
            'financial_data': {'estimated_revenue_leak': f"{leak}%", 'potential_recovery_gain': f"{gain}%"}
        }

    except Exception as e:
        return {
            'url': url,
            'grade': 'Partial',
            'score': 40,
            'metrics': {'Status': {"val": "Limited access – partial scan", "status": "WARN"}},
            'broken_links': [],
            'financial_data': {'estimated_revenue_leak': 'N/A', 'potential_recovery_gain': 'N/A'}
        }

@app.post('/audit')
async def audit(data: dict):
    url = data.get('url')
    if not url: raise HTTPException(400, "URL required")
    result = run_live_audit(url)
    db = SessionLocal()
    record = AuditRecord(**result)
    db.add(record); db.commit(); db.refresh(record); db.close()
    return {'id': record.id, 'data': result}

@app.get('/download/{id}')
async def download(id: int):
    db = SessionLocal()
    r = db.query(AuditRecord).get(id)
    db.close()
    if not r: raise HTTPException(404)
    pdf = ElitePDF()
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 10, f"Audit: {r.url} | Grade: {r.grade} ({r.score}%)", ln=1)
    # Add more content...
    return Response(pdf.output(dest='S').encode('latin-1'), media_type='application/pdf')
