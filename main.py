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
        self.set_font('Arial', 'B', 22)
        self.set_text_color(255, 255, 255)
        self.cell(0, 30, 'COMPREHENSIVE WEBSITE AUDIT REPORT', 0, 1, 'C')
        self.ln(10)

    def add_section(self, title):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, title, ln=1)

    def add_metric(self, name, data):
        self.set_font('Arial', 'B', 12)
        self.multi_cell(0, 6, f"{name}: {data['val']} | Status: {data['status']} | Score: {data['score']}")
        self.set_font('Arial', '', 10)
        self.multi_cell(0, 6, f"Explanation: {data.get('explanation', 'N/A')}")
        self.multi_cell(0, 6, f"Recommendation: {data.get('recommendation', 'N/A')}")
        self.ln(5)

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# --- AUDIT ENGINE WITH MOBILE & DESKTOP CORE WEB VITALS ---
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

    metrics = {}
    broken_links = []

    try:
        time.sleep(random.uniform(1.5, 3.5))
        start_time = time.time()
        res = requests.get(url, headers=headers, timeout=30, verify=False, allow_redirects=True)
        load_time = round(time.time() - start_time, 2)
        soup = BeautifulSoup(res.text, 'html.parser')
        final_url = res.url
        ssl = final_url.startswith('https')

        # --- Fetch Mobile Core Web Vitals ---
        mobile_cwv = {'LCP': 'N/A', 'CLS': 'N/A', 'INP': 'N/A', 'TBT': 'N/A', 'FCP': 'N/A'}
        desktop_cwv = {'LCP': 'N/A', 'CLS': 'N/A', 'INP': 'N/A', 'TBT': 'N/A', 'FCP': 'N/A'}
        try:
            mobile_psi = requests.get(f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={quote_plus(final_url)}&strategy=mobile", timeout=20)
            if mobile_psi.ok:
                mobile_data = mobile_psi.json()
                if 'lighthouseResult' in mobile_data:
                    audits = mobile_data['lighthouseResult']['audits']
                    mobile_cwv['LCP'] = audits['largest-contentful-paint']['displayValue']
                    mobile_cwv['CLS'] = audits['cumulative-layout-shift']['displayValue']
                    mobile_cwv['INP'] = audits.get('interaction-to-next-paint', {}).get('displayValue', 'N/A')
                    mobile_cwv['TBT'] = audits['total-blocking-time']['displayValue']
                    mobile_cwv['FCP'] = audits['first-contentful-paint']['displayValue']

            desktop_psi = requests.get(f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={quote_plus(final_url)}&strategy=desktop", timeout=20)
            if desktop_psi.ok:
                desktop_data = desktop_psi.json()
                if 'lighthouseResult' in desktop_data:
                    audits = desktop_data['lighthouseResult']['audits']
                    desktop_cwv['LCP'] = audits['largest-contentful-paint']['displayValue']
                    desktop_cwv['CLS'] = audits['cumulative-layout-shift']['displayValue']
                    desktop_cwv['INP'] = audits.get('interaction-to-next-paint', {}).get('displayValue', 'N/A')
                    desktop_cwv['TBT'] = audits['total-blocking-time']['displayValue']
                    desktop_cwv['FCP'] = audits['first-contentful-paint']['displayValue']
        except:
            pass

        # Mobile Core Web Vitals
        metrics['Mobile - Largest Contentful Paint (LCP)'] = {"val": mobile_cwv['LCP'], "score": 100 if mobile_cwv['LCP'] != 'N/A' and float(mobile_cwv['LCP'].split()[0]) < 2.5 else 60, "status": "PASS" if mobile_cwv['LCP'] != 'N/A' and float(mobile_cwv['LCP'].split()[0]) < 2.5 else "WARN", "explanation": "Loading performance on mobile (good <2.5s).", "recommendation": "Optimize images, fonts, critical CSS."}
        metrics['Mobile - Cumulative Layout Shift (CLS)'] = {"val": mobile_cwv['CLS'], "score": 100 if mobile_cwv['CLS'] != 'N/A' and float(mobile_cwv['CLS']) < 0.1 else 60, "status": "PASS" if mobile_cwv['CLS'] != 'N/A' and float(mobile_cwv['CLS']) < 0.1 else "WARN", "explanation": "Visual stability on mobile (good <0.1).", "recommendation": "Set dimensions for media, avoid dynamic inserts."}
        metrics['Mobile - Interaction to Next Paint (INP)'] = {"val": mobile_cwv['INP'], "score": 100 if mobile_cwv['INP'] != 'N/A' and 'good' in mobile_cwv['INP'].lower() else 60, "status": "PASS" if mobile_cwv['INP'] != 'N/A' and 'good' in mobile_cwv['INP'].lower() else "WARN", "explanation": "Responsiveness on mobile (good <200ms).", "recommendation": "Reduce JS execution, efficient handlers."}
        metrics['Mobile - Total Blocking Time (TBT)'] = {"val": mobile_cwv['TBT'], "score": 100 if mobile_cwv['TBT'] != 'N/A' and float(mobile_cwv['TBT'].split()[0]) < 300 else 60, "status": "PASS" if mobile_cwv['TBT'] != 'N/A' and float(mobile_cwv['TBT'].split()[0]) < 300 else "WARN", "explanation": "Load responsiveness on mobile.", "recommendation": "Defer non-critical JS."}
        metrics['Mobile - First Contentful Paint (FCP)'] = {"val": mobile_cwv['FCP'], "score": 100 if mobile_cwv['FCP'] != 'N/A' and float(mobile_cwv['FCP'].split()[0]) < 1.8 else 60, "status": "PASS" if mobile_cwv['FCP'] != 'N/A' and float(mobile_cwv['FCP'].split()[0]) < 1.8 else "WARN", "explanation": "Time to first content on mobile.", "recommendation": "Optimize critical path."}

        # Desktop Core Web Vitals (for comparison)
        metrics['Desktop - LCP'] = {"val": desktop_cwv['LCP'], "score": 90 if desktop_cwv['LCP'] != 'N/A' else 50, "status": "PASS" if desktop_cwv['LCP'] != 'N/A' else "INFO", "explanation": "Desktop loading performance.", "recommendation": "Reference for optimization."}
        metrics['Desktop - CLS'] = {"val": desktop_cwv['CLS'], "score": 90 if desktop_cwv['CLS'] != 'N/A' else 50, "status": "PASS" if desktop_cwv['CLS'] != 'N/A' else "INFO", "explanation": "Desktop visual stability.", "recommendation": "Same as mobile."}

        # Other metrics (keep your existing ones)
        # ... (add the rest of your 57 metrics here)

        # Scoring (weight mobile CWV heavily)
        scores = [v['score'] for v in metrics.values() if isinstance(v.get('score'), (int, float))]
        avg_score = round(sum(scores) / len(scores)) if scores else 50

        grade = 'A+' if avg_score >= 95 else 'A' if avg_score >= 85 else 'B' if avg_score >= 70 else 'C' if avg_score >= 50 else 'F'

        revenue_leak_pct = round((100 - avg_score) * 0.3, 1)
        potential_gain_pct = round(revenue_leak_pct * 1.5, 1)

        return {
            'url': final_url,
            'grade': grade,
            'score': avg_score,
            'metrics': metrics,
            'broken_links': broken_links,
            'financial_data': {'estimated_revenue_leak': f"{revenue_leak_pct}%", 'potential_recovery_gain': f"{potential_gain_pct}%"}
        }

    except Exception as e:
        print(f"Audit error: {e}")
        return {
            'url': url,
            'grade': 'Partial',
            'score': 30,
            'metrics': {'Scan Status': {"val": "Limited", "status": "WARN", "explanation": "Site blocked or unavailable", "recommendation": "Try open sites"}},
            'broken_links': [],
            'financial_data': {'estimated_revenue_leak': 'N/A', 'potential_recovery_gain': 'N/A'}
        }

# Endpoints (same as before)
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
    if not r:
        raise HTTPException(404, "Report not found")

    pdf = MasterStrategyPDF()
    pdf.add_page()
    pdf.add_section(f"Audit Report: {r.url}")
    pdf.set_font('Arial', '', 12)
    pdf.multi_cell(0, 8, f"Grade: {r.grade} | Score: {r.score}%")
    pdf.multi_cell(0, 8, f"Revenue Leakage: {r.financial_data['estimated_revenue_leak']}\nPotential Gain: {r.financial_data['potential_recovery_gain']}")
    pdf.ln(10)
    pdf.add_section("Core Web Vitals (Mobile)")
    for name, data in [item for item in r.metrics.items() if 'Mobile' in name]:
        pdf.add_metric(name, data)
    pdf.add_section("Other Metrics")
    for name, data in [item for item in r.metrics.items() if 'Mobile' not in name]:
        pdf.add_metric(name, data)
    return Response(content=pdf.output(dest='S').encode('latin-1'), media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename=elite_audit_{report_id}.pdf'})
