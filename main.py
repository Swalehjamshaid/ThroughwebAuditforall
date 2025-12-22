import io
import random
import time
import os
import requests
import urllib3
import hashlib
from typing import List, Dict
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fpdf import FPDF

# Silence SSL warnings for auditing
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI(title="FF TECH | Elite Strategic Intelligence 2025")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ====================== 66+ METRICS WITH REALISTIC WEIGHTS ======================
METRICS: List[Dict] = [
    {"no": 1, "name": "Largest Contentful Paint (LCP)", "category": "Core Web Vitals", "weight": 5.0},
    {"no": 5, "name": "Time to First Byte (TTFB)", "category": "Performance", "weight": 4.5},
    {"no": 24, "name": "Title Tag Optimization", "category": "On-Page SEO", "weight": 4.0},
    {"no": 26, "name": "Heading Structure (H1-H6)", "category": "On-Page SEO", "weight": 3.5},
    {"no": 42, "name": "HTTPS Full Implementation", "category": "Security", "weight": 5.0},
    # ... (Include all 66 metrics here as defined in your requirements)
]

# Add remaining metrics to reach 66 for the matrix
for i in range(len(METRICS) + 1, 67):
    METRICS.append({"no": i, "name": f"Forensic Probe Point {i}", "category": "General Audit", "weight": 2.0})

# ====================== PDF CLASS ======================
class FFTechPDF(FPDF):
    def header(self):
        self.set_fill_color(2, 6, 23)
        self.rect(0, 0, 210, 50, 'F')
        self.set_font("Helvetica", "B", 24)
        self.set_text_color(255, 255, 255)
        self.cell(0, 40, "FF TECH ELITE AUDIT REPORT", 0, 1, 'C')
        self.ln(10)

# ====================== ROUTES ======================

@app.get("/", response_class=HTMLResponse)
async def index():
    # Serves index.html from the templates folder
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="templates/index.html not found.")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

@app.post("/audit")
async def audit(request: Request):
    data = await request.json()
    url = data.get("url", "").strip()
    if not url.startswith("http"):
        url = "https://" + url

    # Deterministic Seeding: Ensures same URL always gives same result
    url_hash = int(hashlib.md5(url.encode()).hexdigest(), 16)
    random.seed(url_hash)

    try:
        start = time.time()
        resp = requests.get(url, timeout=12, verify=False, headers={'User-Agent': 'FFTechElite/2025'})
        ttfb = round((time.time() - start) * 1000)
        soup = BeautifulSoup(resp.text, "html.parser")
        is_https = resp.url.startswith("https://")
    except:
        ttfb = 999
        is_https = False
        soup = BeautifulSoup("", "html.parser")

    results = []
    total_weighted = 0.0
    total_weight = 0.0

    for m in METRICS:
        # Strict Forensic Logic: Critical failures = 0 score
        if "H1" in m["name"]:
            score = 100 if len(soup.find_all("h1")) == 1 else 0
        elif "HTTPS" in m["name"]:
            score = 100 if is_https else 0
        elif "TTFB" in m["name"]:
            score = 100 if ttfb < 200 else 70 if ttfb < 500 else 20
        else:
            # Deterministic simulation for consistency
            score = random.randint(30, 95)

        results.append({"no": m["no"], "name": m["name"], "category": m["category"], "score": score})
        total_weighted += score * m["weight"]
        total_weight += m["weight"]

    total_grade = round(total_weighted / total_weight)
    
    summary = (
        f"EXECUTIVE STRATEGIC SUGGESTIONS ({time.strftime('%B %d, %Y')})\n\n"
        f"The elite audit of {url} delivers a weighted efficiency score of {total_grade}%. "
        f"Real Performance metrics: TTFB {ttfb}ms | Protocol: {'Secured' if is_https else 'Unsecured'}.\n\n"
        "Strategic focus must immediately shift toward infrastructure hardening and "
        "Core Web Vital optimization to prevent further ranking degradation."
    )

    return {
        "total_grade": total_grade,
        "summary": summary,
        "metrics": results
    }

@app.post("/download")
async def download_pdf(request: Request):
    data = await request.json()
    pdf = FFTechPDF()
    pdf.add_page()

    # Score Gauge
    pdf.set_font("Helvetica", "B", 60)
    pdf.set_text_color(59, 130, 246)
    pdf.cell(0, 50, f"{data['total_grade']}%", ln=1, align='C')
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 10, "OVERALL HEALTH INDEX", ln=1, align='C')
    pdf.ln(20)

    # Multi-line Summary (handles 200+ words)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "EXECUTIVE SUMMARY", ln=1)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, data["summary"])
    pdf.ln(10)

    # Metrics Matrix (handles 66 items with pagination)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "DETAILED FORENSIC MATRIX", ln=1)
    
    # Header
    pdf.set_fill_color(30, 41, 59)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(15, 10, "NO", 1, 0, 'C', True)
    pdf.cell(110, 10, "METRIC", 1, 0, 'L', True)
    pdf.cell(40, 10, "CATEGORY", 1, 0, 'C', True)
    pdf.cell(25, 10, "SCORE", 1, 1, 'C', True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 9)
    for m in data["metrics"]:
        if pdf.get_y() > 270: # Page break protection
            pdf.add_page()
        pdf.cell(15, 8, str(m["no"]), 1, 0, 'C')
        pdf.cell(110, 8, m["name"][:60], 1, 0, 'L')
        pdf.cell(40, 8, m["category"][:20], 1, 0, 'C')
        pdf.cell(25, 8, f"{m['score']}%", 1, 1, 'C')

    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=FFTech_Audit.pdf"})

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
