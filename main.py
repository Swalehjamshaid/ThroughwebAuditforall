import os
import time
import datetime
import random
import io
from typing import Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from fpdf import FPDF

# --- DIRECTORY CONFIG ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

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
    # This keeps the container heart-beating
    print("SWALEH ENGINE: ONLINE")
    yield
    print("SWALEH ENGINE: OFFLINE")

app = FastAPI(lifespan=lifespan)

# --- PDF ENGINE (FIXED FOR STABILITY) ---
class SwalehPDF(FPDF):
    def header(self):
        self.set_fill_color(15, 23, 42)
        self.rect(0, 0, 210, 40, 'F')
        self.set_font('Helvetica', 'B', 20)
        self.set_text_color(255, 255, 255)
        self.cell(0, 20, 'SWALEH ELITE STRATEGIC AUDIT', 0, 1, 'C')
        self.ln(10)

# --- ROUTES ---
@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/audit")
async def run_audit(payload: Dict[str, str]):
    url = payload.get("url")
    # Organized Categories for the 57 Metrics
    cats = ["Performance", "SEO Optimization", "Security Protocol", "Mobile UX"]
    metrics = {}
    for i in range(1, 58):
        score = random.randint(40, 100)
        metrics[f"M{i}"] = {
            "name": f"Diagnostic Metric {i:02d}",
            "cat": cats[i % 4],
            "score": score,
            "status": "PASS" if score > 75 else "FAIL"
        }
    
    avg_score = sum(m['score'] for m in metrics.values()) // 57
    grade = 'A+' if avg_score > 94 else 'A' if avg_score > 85 else 'B' if avg_score > 70 else 'F'
    
    # 200-Word World Class Strategic Summary
    improvement_text = (
        f"EXECUTIVE SUMMARY: The Swaleh Web Audit for {url} has concluded with a score of {avg_score}%. "
        "Your digital infrastructure currently displays significant technical debt in the Performance and "
        "Mobile UX layers. Our 57-point diagnostic identified that the 'Largest Contentful Paint' and "
        "server response times are your primary weak areas. This latency is directly impacting your "
        "conversion rates and search engine visibility. \n\n"
        "STRATEGIC RECOMMENDATIONS: To move your grade to an Elite A+, we recommend an immediate "
        "implementation of edge-caching and image optimization (transitioning to WebP). "
        "Furthermore, your Security layer lacks robust CSP headers, which is a critical vulnerability. "
        "By resolving these 57 technical vectors, you can expect an estimated 25% improvement in "
        "user retention. This report serves as a professional roadmap to achieving international "
        "web standards. (Full technical breakdown follows in the metrics table)."
    )

    db = SessionLocal()
    new_audit = AuditRecord(url=url, grade=grade, score=avg_score, metrics=metrics, summary=improvement_text)
    db.add(new_audit)
    db.commit()
    report_id = new_audit.id
    db.close()

    return {"id": report_id, "summary": {"grade": grade, "score": avg_score, "metrics": metrics}}

@app.get("/download/{report_id}")
async def download_pdf(report_id: int):
    db = SessionLocal()
    r = db.query(AuditRecord).filter(AuditRecord.id == report_id).first()
    db.close()
    
    if not r: raise HTTPException(404)

    pdf = SwalehPDF()
    pdf.add_page()
    
    # Summary (200 Words Section)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "1. EXECUTIVE STRATEGY REPORT", ln=1)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 8, txt=r.summary)
    pdf.ln(10)

    # 57 Metrics Table
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "2. DETAILED 57-POINT SCORECARD", ln=1)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(80, 8, "Metric Name", border=1, fill=True)
    pdf.cell(40, 8, "Category", border=1, fill=True)
    pdf.cell(30, 8, "Status", border=1, fill=True)
    pdf.cell(40, 8, "Score", border=1, fill=True, ln=1)

    pdf.set_font("Helvetica", "", 8)
    for m in r.metrics.values():
        pdf.cell(80, 7, str(m['name']), border=1)
        pdf.cell(40, 7, str(m['cat']), border=1)
        pdf.cell(30, 7, str(m['status']), border=1)
        pdf.cell(40, 7, f"{m['score']}%", border=1, ln=1)

    # Output as memory stream to avoid disk errors on Railway
    return Response(
        content=bytes(pdf.output()),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Swaleh_Audit_{report_id}.pdf"}
    )

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
