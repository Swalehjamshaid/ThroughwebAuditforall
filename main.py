import os
import time
import datetime
import requests
from bs4 import BeautifulSoup
from fpdf import FPDF
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, Response, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from sqlalchemy import create_engine, Column, Integer, String, Float, JSON, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# --- DATABASE SETUP ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AuditRecord(Base):
    __tablename__ = "audit_reports"
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String)
    grade = Column(String)
    score = Column(Integer)
    metrics = Column(JSON)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)

# --- APP INITIALIZATION ---
app = FastAPI(title="FF Tech SaaS")
templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- AUDIT ENGINE LOGIC ---
def run_website_audit(url: str):
    if not url.startswith('http'): url = 'https://' + url
    try:
        start = time.time()
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Metric Logic
        m = {
            "load_time": f"{round(time.time() - start, 2)}s",
            "ssl_active": url.startswith('https'),
            "title_found": soup.title is not None,
            "h1_count": len(soup.find_all('h1')),
            "images_count": len(soup.find_all('img')),
            "meta_desc": soup.find('meta', attrs={'name': 'description'}) is not None
        }
        
        score = sum([20 if m["ssl_active"] else 0, 20 if m["title_found"] else 0, 
                     20 if m["h1_count"] > 0 else 0, 20 if m["meta_desc"] else 0, 20])
        grade = "A" if score >= 80 else "B" if score >= 60 else "C"
        
        return {"url": url, "grade": grade, "score": score, "metrics": m}
    except:
        return None

# --- PDF ENGINE ---
class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'FF TECH CERTIFIED AUDIT', 0, 1, 'C')

def generate_pdf(data):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"Target URL: {data.url}", 1, 1)
    pdf.cell(0, 10, f"Final Grade: {data.grade} | Score: {data.score}", 0, 1)
    for k, v in data.metrics.items():
        pdf.cell(0, 10, f"{k.replace('_',' ')}: {v}", 0, 1)
    return pdf.output(dest='S').encode('latin-1')

# --- ROUTES ---
@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/audit")
def do_audit(data: dict, db: Session = Depends(get_db)):
    result = run_website_audit(data['url'])
    if not result: raise HTTPException(400, "Audit Failed")
    
    db_report = AuditRecord(**result)
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return {"id": db_report.id, "data": result}

@app.get("/download/{report_id}")
def download(report_id: int, db: Session = Depends(get_db)):
    report = db.query(AuditRecord).filter(AuditRecord.id == report_id).first()
    pdf = generate_pdf(report)
    return Response(content=pdf, media_type="application/pdf")
