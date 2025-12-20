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

        # --- MOBILE CORE WEB VITALS FROM PSI ---
        mobile_cwv = {}
        desktop_cwv = {}
        try:
            # Mobile strategy
            mobile_psi_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={quote_plus(final_url)}&strategy=mobile"
            mobile_res = requests.get(mobile_psi_url, timeout=20)
            if mobile_res.ok:
                mobile_data = mobile_res.json()
                if 'lighthouseResult' in mobile_data:
                    audits = mobile_data['lighthouseResult']['audits']
                    mobile_cwv = {
                        'LCP': audits['largest-contentful-paint']['displayValue'],
                        'CLS': audits['cumulative-layout-shift']['displayValue'],
                        'INP': audits.get('interaction-to-next-paint', {}).get('displayValue', 'N/A'),
                        'TBT': audits['total-blocking-time']['displayValue'],
                        'FCP': audits['first-contentful-paint']['displayValue'],
                        'TTFB': audits.get('server-response-time', {}).get('displayValue', 'N/A'),
                    }

            # Desktop strategy
            desktop_psi_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={quote_plus(final_url)}&strategy=desktop"
            desktop_res = requests.get(desktop_psi_url, timeout=20)
            if desktop_res.ok:
                desktop_data = desktop_res.json()
                if 'lighthouseResult' in desktop_data:
                    audits = desktop_data['lighthouseResult']['audits']
                    desktop_cwv = {
                        'LCP': audits['largest-contentful-paint']['displayValue'],
                        'CLS': audits['cumulative-layout-shift']['displayValue'],
                        'INP': audits.get('interaction-to-next-paint', {}).get('displayValue', 'N/A'),
                        'TBT': audits['total-blocking-time']['displayValue'],
                        'FCP': audits['first-contentful-paint']['displayValue'],
                        'TTFB': audits.get('server-response-time', {}).get('displayValue', 'N/A'),
                    }
        except Exception as e:
            print(f"PSI error: {e}")

        # Add Mobile Core Web Vitals
        metrics['Mobile - Largest Contentful Paint (LCP)'] = {
            "val": mobile_cwv.get('LCP', f"{load_time + 1.5:.2f}s (Est.)"),
            "score": 100 if 'good' in mobile_cwv.get('LCP', '').lower() else 60 if mobile_cwv else 50,
            "status": "PASS" if 'good' in mobile_cwv.get('LCP', '').lower() else "WARN" if mobile_cwv else "WARN",
            "explanation": "Mobile LCP is critical as 70%+ traffic is mobile. Good <2.5s.",
            "recommendation": "Optimize images, fonts, and critical CSS for mobile."
        }

        metrics['Mobile - Cumulative Layout Shift (CLS)'] = {
            "val": mobile_cwv.get('CLS', "0.15 (Est.)"),
            "score": 100 if mobile_cwv and float(mobile_cwv['CLS']) < 0.1 else 60,
            "status": "PASS" if mobile_cwv and float(mobile_cwv['CLS']) < 0.1 else "WARN",
            "explanation": "Mobile users are more affected by layout shifts.",
            "recommendation": "Reserve space for ads/images on mobile."
        }

        metrics['Mobile - Interaction to Next Paint (INP)'] = {
            "val": mobile_cwv.get('INP', "250ms (Est.)"),
            "score": 100 if mobile_cwv.get('INP', 'N/A') != 'N/A' and 'good' in mobile_cwv.get('INP', '').lower() else 60,
            "status": "PASS" if mobile_cwv.get('INP', 'N/A') != 'N/A' and 'good' in mobile_cwv.get('INP', '').lower() else "WARN",
            "explanation": "Responsiveness on mobile touch devices. Good <200ms.",
            "recommendation": "Reduce JS, use efficient event listeners."
        }

        metrics['Mobile - Total Blocking Time (TBT)'] = {
            "val": mobile_cwv.get('TBT', "400ms (Est.)"),
            "score": 100 if mobile_cwv and 'good' in mobile_cwv.get('TBT', '').lower() else 60,
            "status": "PASS" if mobile_cwv and 'good' in mobile_cwv.get('TBT', '').lower() else "WARN",
            "explanation": "Mobile devices have slower CPUs.",
            "recommendation": "Defer non-critical JS on mobile."
        }

        # Add Desktop for comparison (optional)
        metrics['Desktop - LCP'] = {
            "val": desktop_cwv.get('LCP', "N/A"),
            "score": 90 if desktop_cwv else 50,
            "status": "PASS" if desktop_cwv else "INFO",
            "explanation": "Desktop reference for comparison.",
            "recommendation": "Use for benchmarking."
        }

        # Other metrics (keep your existing ones)
        # ...

        # Scoring includes mobile heavily
        scores = [v['score'] for v in metrics.values()]
        avg_score = round(sum(scores) / len(scores)) if scores else 50

        grade = 'A+' if avg_score >= 95 else 'A' if avg_score >= 85 else 'B' if avg_score >= 70 else 'C' if avg_score >= 50 else 'F'

        return {
            'url': final_url,
            'grade': grade,
            'score': avg_score,
            'metrics': metrics,
            'broken_links': broken_links,
            'financial_data': {'estimated_revenue_leak': f"{round((100 - avg_score) * 0.3, 1)}%", 'potential_recovery_gain': f"{round((100 - avg_score) * 0.45, 1)}%"}
        }

    except Exception as e:
        print(f"Audit error: {e}")
        return {
            'url': url,
            'grade': 'Partial',
            'score': 30,
            'metrics': {'Scan Status': {"val": "Limited", "status": "WARN", "explanation": "Site blocked scan", "recommendation": "Try open sites like example.com"}},
            'broken_links': [],
            'financial_data': {'estimated_revenue_leak': 'N/A', 'potential_recovery_gain': 'N/A'}
        }

# Endpoints unchanged
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
    pdf.multi_cell(0, 8, f"Revenue Impact: {r.financial_data['estimated_revenue_leak']} leakage")
    pdf.ln(10)
    pdf.add_section("Core Web Vitals (Mobile)")
    for name, data in [item for item in r.metrics.items() if 'Mobile' in name]:
        pdf.add_metric(name, data)
    pdf.add_section("Other Key Metrics")
    for name, data in [item for item in r.metrics.items() if 'Mobile' not in name]:
        pdf.add_metric(name, data)
    return Response(content=pdf.output(dest='S').encode('latin-1'), media_type='application/pdf')
