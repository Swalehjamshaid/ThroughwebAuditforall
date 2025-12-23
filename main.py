import asyncio
import time
import io
import os
from typing import List, Dict
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates

from bs4 import BeautifulSoup
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

app = FastAPI(title="FF TECH ELITE v3.0 - PDF Fix Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

if not os.path.exists("templates"):
    os.makedirs("templates")

templates = Jinja2Templates(directory="templates")

# ==================== CONFIGURATION ====================
CATEGORIES = ["Performance", "SEO", "UX", "Security"]
PILLAR_WEIGHTS = {"Performance": 0.4, "SEO": 0.3, "UX": 0.2, "Security": 0.1}

# Metric name, category, weight (1=minor, 3=important, 5=critical)
METRICS_LIST = [
    ("Largest Contentful Paint (LCP)", "Performance", 5),
    ("First Contentful Paint (FCP)", "Performance", 5),
    ("Time to First Byte (TTFB)", "Performance", 5),
    ("Cumulative Layout Shift (CLS)", "Performance", 5),
    ("Total Blocking Time (TBT)", "Performance", 3),
    ("Page Weight (KB)", "Performance", 3),
    ("Number of Requests", "Performance", 3),
    ("Image Optimization", "Performance", 3),
    ("JavaScript Minification", "Performance", 2),
    ("Font Display Strategy", "Performance", 2),

    ("Page Title (Length & Quality)", "SEO", 5),
    ("Meta Description (Length & Quality)", "SEO", 5),
    ("Canonical Tag Present", "SEO", 3),
    ("H1 Tag Unique & Present", "SEO", 3),
    ("Heading Structure (H2-H6)", "SEO", 2),
    ("Image Alt Attributes", "SEO", 3),
    ("Robots Meta Tag", "SEO", 2),
    ("Open Graph Tags", "SEO", 2),
    ("Structured Data (Schema.org)", "SEO", 3),
    ("Internal Links Quality", "SEO", 2),

    ("Viewport Meta Tag", "UX", 3),
    ("Mobile-Friendly Design", "UX", 5),
    ("Tap Target Spacing", "UX", 2),
    ("Readable Font Sizes", "UX", 2),
    ("Color Contrast Ratio", "UX", 2),
    ("Favicon Present", "UX", 1),
    ("No Console Errors", "UX", 3),
    ("Fast Interactivity", "UX", 3),
    ("Touch Icons", "UX", 1),
    ("Error Messages Clear", "UX", 1),

    ("HTTPS Enforced", "Security", 5),
    ("HSTS Header", "Security", 3),
    ("Content-Security-Policy Header", "Security", 5),
    ("X-Frame-Options Header", "Security", 3),
    ("X-Content-Type-Options Header", "Security", 3),
    ("Referrer-Policy Header", "Security", 2),
    ("No Mixed Content", "Security", 3),
    ("Secure Cookies", "Security", 3),
    ("Vulnerable JS Libraries", "Security", 5),
    ("Permissions-Policy Header", "Security", 2),
]

# ==================== REAL AUDIT FUNCTION ====================
async def run_real_audit(url: str, mobile: bool) -> Dict:
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("Playwright not installed.")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        viewport = {"width": 390, "height": 844} if mobile else {"width": 1366, "height": 768}
        context = await browser.new_context(viewport=viewport)
        page = await context.new_page()
        start_time = time.time()
        try:
            response = await page.goto(url, wait_until="networkidle", timeout=60000)
            if not response or response.status >= 400:
                raise Exception(f"Page failed to load (status: {response.status if response else 'None'})")
            ttfb = int((time.time() - start_time) * 1000)
            metrics_js = await page.evaluate("""() => {
                const paint = performance.getEntriesByType('paint');
                const lcpEntries = performance.getEntriesByType('largest-contentful-paint');
                const resources = performance.getEntriesByType('resource');
                const fcp = paint.find(e => e.name === 'first-contentful-paint')?.startTime || 0;
                const lcp = lcpEntries[lcpEntries.length - 1]?.startTime || 0;
                let totalSize = 0;
                resources.forEach(r => { if (r.transferSize) totalSize += r.transferSize; });
                return {
                    fcp: Math.round(fcp),
                    lcp: Math.round(lcp),
                    totalBytes: totalSize,
                    requestCount: resources.length,
                    cls: performance.getEntriesByType('layout-shift')
                        .filter(e => !e.hadRecentInput)
                        .reduce((sum, e) => sum + e.value, 0)
                };
            }""")
            html = await page.content()
            headers = {k.lower(): v for k, v in response.headers.items()}
            await browser.close()
            return {
                "ttfb": ttfb,
                "fcp": metrics_js["fcp"],
                "lcp": metrics_js["lcp"],
                "cls": round(metrics_js["cls"], 3),
                "page_weight_kb": round(metrics_js["totalBytes"] / 1024),
                "request_count": metrics_js["requestCount"],
                "html": html,
                "headers": headers,
                "final_url": response.url
            }
        except Exception as e:
            await browser.close()
            raise e

# ==================== AUDIT SCORING ====================
def generate_audit_results(audit_data: Dict, soup: BeautifulSoup) -> Dict:
    perf = audit_data
    headers = perf.get("headers", {})
    metrics = []
    pillar_scores = {cat: [] for cat in CATEGORIES}
    low_score_issues = []

    for i, (name, category, weight) in enumerate(METRICS_LIST, 1):
        score = 90
        if category == "Performance":
            if "LCP" in name: score = 100 if perf["lcp"] <= 2500 else 50
            elif "FCP" in name: score = 100 if perf["fcp"] <= 1800 else 50
            elif "TTFB" in name: score = 100 if perf["ttfb"] <= 800 else 50
            elif "CLS" in name: score = 100 if perf["cls"] <= 0.1 else 50
        elif category == "SEO":
            if "Title" in name: score = 100 if soup.title else 30
            elif "Meta Description" in name: score = 100 if soup.find("meta", {"name": "description"}) else 30
        elif category == "UX":
            if "Viewport" in name: score = 100 if soup.find("meta", {"name": "viewport"}) else 30
        elif category == "Security":
            if "HTTPS" in name: score = 100 if perf["final_url"].startswith("https://") else 0

        # Apply weighted scoring
        score = max(0, min(100, int(score * (weight/5))))
        metrics.append({"no": i, "name": name, "category": category, "score": score})
        pillar_scores[category].append(score)
        if score < 80: low_score_issues.append({"issue": name, "score": score})

    pillar_avg = {cat: round(sum(scores)/len(scores)) if scores else 100 for cat, scores in pillar_scores.items()}
    total_grade = round(sum(pillar_avg[cat] * PILLAR_WEIGHTS[cat] for cat in CATEGORIES))

    # Roadmap
    roadmap = "<b>Website Improvement Roadmap</b><br><ul>"
    for item in low_score_issues[:20]:
        roadmap += f"<li>{item['issue']}: Improve to increase score.</li>"
    roadmap += "</ul>"

    summary = f"LCP {perf['lcp']}ms • FCP {perf['fcp']}ms • TTFB {perf['ttfb']}ms • CLS {perf['cls']} • Weight {perf['page_weight_kb']}KB"
    return {"metrics": metrics, "pillar_avg": pillar_avg, "total_grade": total_grade, "summary": summary, "roadmap": roadmap}

# ==================== ENDPOINTS ====================
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/audit")
async def audit(request: Request):
    try:
        data = await request.json()
        raw_url = data.get("url", "").strip()
        mobile = data.get("mode", "desktop") == "mobile"
        if not raw_url: raise HTTPException(400, "URL required")
        if not raw_url.startswith(("http://","https://")): raw_url = "https://" + raw_url
        audit_data = await run_real_audit(raw_url, mobile)
        soup = BeautifulSoup(audit_data["html"], "html.parser")
        results = generate_audit_results(audit_data, soup)
        results["url"] = audit_data["final_url"]
        results["audited_at"] = time.strftime("%B %d, %Y at %H:%M UTC")
        return results
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/download")
async def download_pdf(request: Request):
    try:
        data = await request.json()
        metrics = data.get("metrics", [])
        pillar_avg = data.get("pillars", {})
        total_grade = data.get("total_grade", 0)
        summary = data.get("summary", "")
        roadmap = data.get("roadmap", "")

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=60, bottomMargin=50)
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='TitleBold', fontSize=18, leading=22, alignment=1, textColor=colors.HexColor("#0f766e")))
        story = []
        story.append(Paragraph("FF TECH ELITE - Web Audit Report", styles['TitleBold']))
        story.append(Spacer(1, 15))
        story.append(Paragraph(f"<b>URL:</b> {data.get('url','')}", styles['Normal']))
        story.append(Paragraph(f"<b>Audit Date:</b> {data.get('audited_at','')}", styles['Normal']))
        story.append(Paragraph(f"<b>Overall Health Score:</b> {total_grade}%", styles['Heading1']))
        story.append(Paragraph(f"<b>Core Metrics:</b> {summary}", styles['Normal']))
        story.append(Spacer(1, 15))

        # Pillars table
        pillar_table = [["Pillar", "Score"]]
        for k,v in pillar_avg.items(): pillar_table.append([k,f"{v}%"])
        t = Table(pillar_table, colWidths=[200,100])
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor("#0f766e")),
                               ('TEXTCOLOR',(0,0),(-1,0),colors.white),
                               ('GRID',(0,0),(-1,-1),0.5,colors.grey)]))
        story.append(t)
        story.append(Spacer(1,15))

        # Metrics table
        table_data = [["#", "Metric","Category","Score"]]
        for m in metrics: table_data.append([str(m['no']), m['name'], m['category'], f"{m['score']}%"])
        mt = Table(table_data, colWidths=[30,250,100,80])
        mt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor("#14b8a6")),
                                ('TEXTCOLOR',(0,0),(-1,0),colors.black),
                                ('GRID',(0,0),(-1,-1),0.5,colors.grey),
                                ('BACKGROUND',(0,1),(-1,-1),colors.HexColor("#e0f2f1")),
                                ('TEXTCOLOR',(0,1),(-1,-1),colors.black)]))
        story.append(mt)
        story.append(PageBreak())

        story.append(Paragraph("Improvement Roadmap", styles['TitleBold']))
        story.append(Spacer(1,15))
        story.append(Paragraph(roadmap, styles['Normal']))

        doc.build(story)
        buffer.seek(0)
        filename = f"FF_ELITE_Audit_{int(time.time())}.pdf"
        return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={filename}"})
    except Exception as e:
        raise HTTPException(500,"PDF generation failed: "+str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT",8080)))
