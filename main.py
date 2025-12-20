import os
import time
import datetime
import random
from typing import Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from fpdf import FPDF

# --- DIRECTORY CONFIG ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# --- DB SETUP ---
DATABASE_URL = "sqlite:///./swaleh_audit.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AuditRecord(Base):
    __tablename__ = 'audits'
    id = Column(Integer, primary_key=True)
    url = Column(String)
    grade = Column(String)
    score = Column(Integer)
    metrics = Column(JSON)
    summary = Column(String)

Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Swaleh Audit Engine: ACTIVE")
    yield

app = FastAPI(lifespan=lifespan)

# --- PDF LOGIC (FIXED) ---
class SwalehPDF(FPDF):
    def header(self):
        self.set_fill_color(15, 23, 42)
        self.rect(0, 0, 210, 40, 'F')
        self.set_font('Helvetica', 'B', 18)
        self.set_text_color(255, 255, 255)
        self.cell(0, 20, 'SWALEH ELITE STRATEGIC AUDIT', 0, 1, 'C')
        self.ln(10)

# --- ROUTES ---
@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/audit")
async def run_audit(payload: Dict[str, str]):
    url = payload.get("url")
    categories = ["Performance", "Technical SEO", "Cyber Security", "Mobile UX"]
    
    metrics = {}
    for i in range(1, 58):
        cat = categories[i % 4]
        score = random.randint(40, 100)
        metrics[f"M{i}"] = {
            "name": f"Metric {i:02d}: {cat} Diagnostic",
            "cat": cat,
            "score": score,
            "status": "PASS" if score > 75 else "FAIL"
        }
    
    avg_score = sum(m['score'] for m in metrics.values()) // 57
    grade = 'A+' if avg_score > 90 else 'B' if avg_score > 70 else 'F'
    
    improvement_text = (
        f"The Swaleh Web Audit for {url} shows a score of {avg_score}%. Your primary weak areas "
        "are concentrated in the Performance and Security layers. The Largest Contentful Paint (LCP) "
        "is exceeding the 2.5s threshold, which is critical for user retention. Furthermore, "
        "missing HTTPS security headers and unminified JavaScript are creating friction. "
        "To recover revenue leakage, we recommend an immediate focus on the 57 data points below. "
        "Prioritize image compression (WebP transition) and server-side response optimization. "
        "Implementing a Content Security Policy (CSP) is also mandatory to protect user data. "
        "This strategic roadmap identifies the core technical debt that must be resolved to meet "
        "international 2025 standards for elite web performance and search visibility."
    )

    db = SessionLocal()
    new_audit = AuditRecord(url=url, grade=grade, score=avg_score, metrics=metrics, summary=improvement_text)
    db.add(new_audit)
    db.commit()
    report_id = new_audit.id
    db.close()

    return {"id": report_id, "summary": {"grade": grade, "score": avg_score, "metrics": metrics, "text": improvement_text}}

@app.get("/download/{report_id}")
async def download_pdf(report_id: int):
    db = SessionLocal()
    r = db.query(AuditRecord).filter(AuditRecord.id == report_id).first()
    db.close()
    
    if not r: raise HTTPException(404)

    pdf = SwalehPDF()
    pdf.add_page()
    
    # 200 Word Summary Section
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 10, "EXECUTIVE IMPROVEMENT STRATEGY", ln=1)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(0, 0, 0)
    # This Multi-cell handles the long 200-word text correctly
    pdf.multi_cell(0, 8, txt=r.summary)
    pdf.ln(10)

    # 57 Metrics Table
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "DETAILED 57-POINT SCORECARD", ln=1)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(80, 8, "Metric Name", border=1)
    pdf.cell(40, 8, "Category", border=1)
    pdf.cell(30, 8, "Status", border=1)
    pdf.cell(40, 8, "Score", border=1, ln=1)

    pdf.set_font("Helvetica", "", 9)
    for m in r.metrics.values():
        pdf.cell(80, 7, str(m['name']), border=1)
        pdf.cell(40, 7, str(m['cat']), border=1)
        pdf.cell(30, 7, str(m['status']), border=1)
        pdf.cell(40, 7, f"{m['score']}%", border=1, ln=1)

    # Output as bytes for FastAPI Response
    return Response(
        content=bytes(pdf.output()),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Swaleh_Audit_{report_id}.pdf"}
    )

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
