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

# --- DATABASE SETUP ---
DB_URL = os.getenv('DATABASE_URL', 'sqlite:///./live_audits.db')
engine = create_engine(DB_URL, connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AuditRecord(Base):
    __tablename__ = 'strategic_reports'
    id = Column(Integer, primary_key=True)
    url = Column(String)
    grade = Column(String)
    score = Column(Integer)
    metrics = Column(JSON)
    broken_links = Column(JSON)
    financial_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory='templates')

# --- PROFESSIONAL PDF GENERATOR ---
class MasterStrategyPDF(FPDF):
    def header(self):
        self.set_fill_color(15, 23, 42)
        self.rect(0, 0, 210, 50, 'F')
        self.set_font('Arial', 'B', 24)
        self.set_text_color(255, 255, 255)
        self.cell(0, 30, 'WORLD-CLASS WEBSITE AUDIT REPORT', 0, 1, 'C')
        self.ln(10)

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# --- STRICT & PROFESSIONAL AUDIT ENGINE (2025 STANDARDS) ---
def run_live_audit(url: str):
    if not re.match(r'^(http|https)://', url):
        url = 'https://' + url

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive'
    }

    try:
        time.sleep(random.uniform(1.5, 3.5))
        start_time = time.time()
        res = requests.get(url, headers=headers, timeout=30, verify=False, allow_redirects=True)
        load_time = round(time.time() - start_time, 2)
        soup = BeautifulSoup(res.text, 'html.parser')
        final_url = res.url
        ssl = final_url.startswith('https')
        status_code = res.status_code

        metrics = {}
        broken_links = []

        # 1. SECURITY & INFRASTRUCTURE (Zero Tolerance)
        metrics['HTTPS Security'] = {
            "val": "Enabled" if ssl else "Disabled",
            "score": 100 if ssl else 0,
            "status": "PASS" if ssl else "FAIL",
            "explanation": "HTTPS is non-negotiable in 2025. Google penalizes non-HTTPS sites in rankings and browsers show warnings, eroding user trust."
        }

        metrics['HTTP Status Code'] = {
            "val": str(status_code),
            "score": 100 if status_code == 200 else 0,
            "status": "PASS" if status_code == 200 else "FAIL",
            "explanation": "Only 200 OK is acceptable. Downtime or errors directly impact revenue and SEO. Monitor uptime rigorously."
        }

        # 2. PERFORMANCE (Very Strict 2025 CWV Thresholds)
        metrics['Page Load Time'] = {
            "val": f"{load_time}s",
            "score": 100 if load_time < 1.5 else 60 if load_time < 2.0 else 30 if load_time < 3.0 else 0,
            "status": "PASS" if load_time < 1.5 else "WARN" if load_time < 2.0 else "FAIL",
            "explanation": "Sub-1.5s load is the new standard. Every additional second can cost 20-30% in conversions."
        }

        # Google PageSpeed Insights Integration
        psi_success = False
        try:
            psi_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={quote_plus(final_url)}&strategy=desktop"
            psi_res = requests.get(psi_url, timeout=15)
            if psi_res.ok:
                psi_data = psi_res.json()
                if 'lighthouseResult' in psi_data:
                    psi_success = True
                    audits = psi_data['lighthouseResult']['audits']

                    lcp = float(audits.get('largest-contentful-paint', {}).get('numericValue', load_time * 1000)) / 1000
                    cls = float(audits.get('cumulative-layout-shift', {}).get('numericValue', 0.1))
                    tbt = float(audits.get('total-blocking-time', {}).get('numericValue', 300))

                    metrics['Largest Contentful Paint (LCP)'] = {
                        "val": f"{lcp:.2f}s",
                        "score": 100 if lcp < 1.5 else 50 if lcp < 2.0 else 0,
                        "status": "PASS" if lcp < 1.5 else "WARN" if lcp < 2.0 else "FAIL",
                        "explanation": "Google's 2025 target: <1.5s for top performance. Impacts Core Web Vitals ranking signal."
                    }

                    metrics['Cumulative Layout Shift (CLS)'] = {
                        "val": f"{cls:.3f}",
                        "score": 100 if cls < 0.05 else 40 if cls < 0.1 else 0,
                        "status": "PASS" if cls < 0.05 else "WARN" if cls < 0.1 else "FAIL",
                        "explanation": "CLS must be <0.05 to avoid frustrating shifts. Critical for user satisfaction and SEO."
                    }

                    metrics['Total Blocking Time (TBT)'] = {
                        "val": f"{tbt:.0f}ms",
                        "score": 100 if tbt < 150 else 50 if tbt < 300 else 0,
                        "status": "PASS" if tbt < 150 else "WARN" if tbt < 300 else "FAIL",
                        "explanation": "TBT <150ms ensures smooth interactivity. High values indicate heavy JavaScript."
                    }
        except Exception as e:
            psi_success = False

        if not psi_success:
            est_lcp = round(load_time + 1.0, 2)
            metrics['Largest Contentful Paint (LCP)'] = {
                "val": f"{est_lcp}s (Est.)",
                "score": 100 if est_lcp < 1.5 else 50 if est_lcp < 2.0 else 0,
                "status": "PASS" if est_lcp < 1.5 else "WARN" if est_lcp < 2.0 else "FAIL",
                "explanation": "Estimated LCP based on load time. Use Lighthouse for precise measurement."
            }

        # 3. SEO FUNDAMENTALS (Strict)
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        title_len = len(title)
        metrics['Page Title'] = {
            "val": f"{title_len} chars",
            "score": 100 if 50 <= title_len <= 60 else 0,
            "status": "PASS" if 50 <= title_len <= 60 else "FAIL",
            "explanation": "Optimal title length is 50-60 characters for full display in Google SERPs."
        }

        meta_desc = soup.find('meta', attrs={'name': 'description'})
        desc_len = len(meta_desc['content'].strip()) if meta_desc else 0
        metrics['Meta Description'] = {
            "val": f"{desc_len} chars",
            "score": 100 if 120 <= desc_len <= 158 else 0,
            "status": "PASS" if 120 <= desc_len <= 158 else "FAIL",
            "explanation": "Meta description should be 120-158 chars to maximize click-through rates."
        }

        h1_count = len(soup.find_all('h1'))
        metrics['H1 Heading'] = {
            "val": f"{h1_count} found",
            "score": 100 if h1_count == 1 else 0,
            "status": "PASS" if h1_count == 1 else "FAIL",
            "explanation": "Exactly one H1 tag is best practice for semantic structure and SEO."
        }

        # 4. ACCESSIBILITY & UX
        viewport = bool(soup.find('meta', attrs={'name': 'viewport'}))
        metrics['Mobile Viewport'] = {
            "val": "Present" if viewport else "Missing",
            "score": 100 if viewport else 0,
            "status": "PASS" if viewport else "FAIL",
            "explanation": "Viewport meta tag is required for responsive design and mobile-friendliness."
        }

        alt_missing = len([img for img in soup.find_all('img') if not img.get('alt') or img['alt'].strip() == ""])
        metrics['Missing Alt Text'] = {
            "val": str(alt_missing),
            "score": 100 if alt_missing == 0 else 0,
            "status": "PASS" if alt_missing == 0 else "FAIL",
            "explanation": "All images must have descriptive alt text for accessibility (WCAG) and SEO."
        }

        # 5. INFRASTRUCTURE INTEGRITY
        for a in soup.find_all('a', href=True)[:20]:
            href = a['href']
            if href.startswith('/') or href.startswith(final_url):
                try:
                    full = requests.compat.urljoin(final_url, href)
                    chk = requests.head(full, headers=headers, timeout=6)
                    if chk.status_code >= 400:
                        broken_links.append(full)
                except:
                    broken_links.append(full)

        metrics['Broken Links'] = {
            "val": str(len(broken_links)),
            "score": 100 if len(broken_links) == 0 else 0,
            "status": "PASS" if len(broken_links) == 0 else "FAIL",
            "explanation": "Broken links damage user experience and SEO authority. Zero tolerance required."
        }

        # Weighted Strict Scoring
        scores = [v['score'] for v in metrics.values()]
        avg_score = round(sum(scores) / len(scores)) if scores else 0

        # Deal-breakers cap the score
        if not ssl or len(broken_links) > 0 or alt_missing > 0 or h1_count != 1:
            avg_score = min(avg_score, 55)

        # Financial Impact (Capped & Realistic)
        leak_base = (100 - avg_score) * 0.3
        leak_issues = len(broken_links) * 2 + alt_missing * 1.2 + (30 if not ssl else 0)
        revenue_leak = round(min(leak_base + leak_issues, 50), 1)
        potential_gain = round(revenue_leak * 1.6, 1)

        grade = 'A+' if avg_score >= 95 else 'A' if avg_score >= 85 else 'B' if avg_score >= 70 else 'C' if avg_score >= 50 else 'D' if avg_score >= 30 else 'F'

        return {
            'url': final_url,
            'grade': grade,
            'score': avg_score,
            'metrics': metrics,
            'broken_links': broken_links,
            'financial_data': {
                'estimated_revenue_leak': f"{revenue_leak}%",
                'potential_recovery_gain': f"{potential_gain}%"
            }
        }

    except Exception as e:
        print(f"Audit failed: {e}")
        return {
            'url': url,
            'grade': 'Partial',
            'score': 30,
            'metrics': {'Status': {"val": "Limited access detected", "status": "WARN", "explanation": "Site may be blocking automated audits or experiencing issues."}},
            'broken_links': [],
            'financial_data': {'estimated_revenue_leak': 'N/A', 'potential_recovery_gain': 'N/A'}
        }

@app.post('/audit')
async def do_audit(data: dict):
    target_url = data.get('url')
    if not target_url:
        raise HTTPException(400, "URL required")
    res = run_live_audit(target_url)
    db = SessionLocal()
    rep = AuditRecord(**res)
    db.add(rep); db.commit(); db.refresh(rep); db.close()
    return {'id': rep.id, 'data': res}

@app.get('/download/{report_id}')
def download(report_id: int):
    db = SessionLocal()
    r = db.query(AuditRecord).filter(AuditRecord.id == report_id).first()
    db.close()
    if not r: raise HTTPException(404)

    pdf = MasterStrategyPDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 18)
    pdf.cell(0, 10, f"Strict Audit Report: {r.url}", ln=1)
    pdf.cell(0, 10, f"Grade: {r.grade} | Score: {r.score}%", ln=1)
    pdf.ln(10)
    pdf.set_font('Arial', '', 12)
    pdf.multi_cell(0, 8, f"Estimated Revenue Leakage: {r.financial_data['estimated_revenue_leak']}\nPotential Recovery: {r.financial_data['potential_recovery_gain']}")
    pdf.ln(10)
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, "Key Metrics & Requirements", ln=1)
    pdf.set_font('Arial', '', 10)
    for name, data in r.metrics.items():
        pdf.multi_cell(0, 6, f"{name}: {data['val']} — {data['status']}")
        pdf.multi_cell(0, 6, f"   {data.get('explanation', '')}")
    return Response(content=pdf.output(dest='S').encode('latin-1'), media_type='application/pdf')
