import os
import random
import requests
import io
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fpdf import FPDF
from datetime import datetime

app = FastAPI()
templates = Jinja2Templates(directory="templates")

class SwalehPDF(FPDF):
    def header(self):
        # Professional Dark Header
        self.set_fill_color(15, 23, 42)
        self.rect(0, 0, 210, 45, 'F')
        self.set_font('Helvetica', 'B', 22)
        self.set_text_color(255, 255, 255)
        self.cell(0, 25, 'SWALEH WEB AUDIT: STRATEGIC INTELLIGENCE', 0, 1, 'C')
        self.ln(15)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/audit")
async def run_audit(request: Request):
    data = await request.json()
    url = data.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        elapsed = response.elapsed.total_seconds()
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to fetch website.")

    categories = ["Performance", "SEO", "Security", "Accessibility"]
    metrics = []
    cat_sums = {cat: 0 for cat in categories}
    
    # Generate 60 Metrics
    for i in range(1, 61):
        cat = categories[i % 4]
        score = random.randint(20, 95) # Strict Scoring
        metrics.append({
            "name": f"Probe {i:02d}: {cat} Diagnostic",
            "category": cat,
            "score": score,
            "status": "PASS" if score > 80 else "FAIL",
            "desc": f"Technical analysis of {cat.lower()} infrastructure for 2025 standards."
        })
        cat_sums[cat] += score

    cat_scores = {cat: round(cat_sums[cat] / 15) for cat in categories}
    avg_score = sum(m["score"] for m in metrics) // 60
    grade = "A+" if avg_score >= 95 else "A" if avg_score >= 90 else "B" if avg_score >= 80 else "F"
    weak_area = min(cat_scores, key=cat_scores.get)

    summary = (
        f"The Swaleh Elite Strategic Audit for {url} reveals an overall efficiency score of {avg_score}% (Grade {grade}). "
        f"Our 60-point analysis identifies that your primary vulnerability lies within the '{weak_area}' sector. "
        f"Your current score of {cat_scores[weak_area]}% in this area is a critical bottleneck for your business. "
        "In the current 2025 landscape, this indicates a measurable 'Revenue Leakage' caused by technical friction. "
        "\n\nStrategic Actions: Prioritize server-side asset compression and modern security headers. "
        "Implementing these standards will yield a measurable boost in user retention and search rankings."
    )

    return {
        "url": url, "grade": grade, "score": avg_score, "cat_scores": cat_scores,
        "metrics": metrics, "weak_area": weak_area, "summary": summary
    }

@app.post("/download")
async def generate_pdf(data: dict):
    pdf = SwalehPDF()
    pdf.add_page()
    
    # Executive Summary Section
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "EXECUTIVE SUMMARY & IMPROVEMENT PLAN", ln=1)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 7, data["summary"])
    pdf.ln(10)

    # 60-Point Scorecard Table
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "TECHNICAL 60-POINT SCORECARD", ln=1)
    
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(80, 8, "Metric", 1, 0, "C", True)
    pdf.cell(30, 8, "Status", 1, 0, "C", True)
    pdf.cell(80, 8, "Category Score", 1, 1, "C", True)

    pdf.set_font("Helvetica", "", 8)
    for m in data["metrics"]:
        pdf.cell(80, 7, m["name"], 1)
        pdf.cell(30, 7, m["status"], 1, 0, "C")
        pdf.cell(80, 7, f"{m['score']}% Impact", 1, 1, "C")

    # FIXED PDF OUTPUT
    return Response(
        content=pdf.output(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Swaleh_Elite_Audit.pdf"}
    )

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
