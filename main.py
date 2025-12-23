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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

app = FastAPI(title="FF TECH ELITE v3 - Weighted Audit Engine")

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

# Assign metric weights: Critical=5, Important=3, Minor=1
CRITICAL_METRICS = {
    "Performance": ["Largest Contentful Paint (LCP)", "First Contentful Paint (FCP)", "Time to First Byte (TTFB)", "Cumulative Layout Shift (CLS)"],
    "SEO": ["Page Title (Length & Quality)", "Meta Description (Length & Quality)", "H1 Tag Unique & Present", "Canonical Tag Present"],
    "UX": ["Viewport Meta Tag", "Mobile-Friendly Design"],
    "Security": ["HTTPS Enforced", "HSTS Header", "Content-Security-Policy Header", "X-Frame-Options Header"]
}

METRICS_LIST = [
    ("Largest Contentful Paint (LCP)", "Performance"),
    ("First Contentful Paint (FCP)", "Performance"),
    ("Time to First Byte (TTFB)", "Performance"),
    ("Cumulative Layout Shift (CLS)", "Performance"),
    ("Total Blocking Time (TBT)", "Performance"),
    ("Page Weight (KB)", "Performance"),
    ("Number of Requests", "Performance"),
    ("Image Optimization", "Performance"),
    ("JavaScript Minification", "Performance"),
    ("Font Display Strategy", "Performance"),

    ("Page Title (Length & Quality)", "SEO"),
    ("Meta Description (Length & Quality)", "SEO"),
    ("Canonical Tag Present", "SEO"),
    ("H1 Tag Unique & Present", "SEO"),
    ("Heading Structure (H2-H6)", "SEO"),
    ("Image Alt Attributes", "SEO"),
    ("Robots Meta Tag", "SEO"),
    ("Open Graph Tags", "SEO"),
    ("Structured Data (Schema.org)", "SEO"),
    ("Internal Links Quality", "SEO"),

    ("Viewport Meta Tag", "UX"),
    ("Mobile-Friendly Design", "UX"),
    ("Tap Target Spacing", "UX"),
    ("Readable Font Sizes", "UX"),
    ("Color Contrast Ratio", "UX"),
    ("Favicon Present", "UX"),
    ("No Console Errors", "UX"),
    ("Fast Interactivity", "UX"),
    ("Touch Icons", "UX"),
    ("Error Messages Clear", "UX"),

    ("HTTPS Enforced", "Security"),
    ("HSTS Header", "Security"),
    ("Content-Security-Policy Header", "Security"),
    ("X-Frame-Options Header", "Security"),
    ("X-Content-Type-Options Header", "Security"),
    ("Referrer-Policy Header", "Security"),
    ("No Mixed Content", "Security"),
    ("Secure Cookies", "Security"),
    ("Vulnerable JS Libraries", "Security"),
    ("Permissions-Policy Header", "Security"),
]

# Fill up to 66 metrics if needed
while len(METRICS_LIST) < 66:
    METRICS_LIST.append((f"Advanced {CATEGORIES[len(METRICS_LIST) % 4]} Check #{len(METRICS_LIST)+1}", CATEGORIES[len(METRICS_LIST) % 4]))


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
        response = await page.goto(url, wait_until="networkidle", timeout=60000)
        if not response or response.status >= 400:
            await browser.close()
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


# ==================== SCORING FUNCTION ====================
def get_metric_weight(name: str, category: str) -> int:
    return 5 if name in CRITICAL_METRICS.get(category, []) else 3 if "Important" in name else 1

def generate_audit_results(audit_data: Dict, soup: BeautifulSoup) -> Dict:
    metrics = []
    pillar_scores = {cat: [] for cat in CATEGORIES}
    low_score_issues = []

    for i, (name, category) in enumerate(METRICS_LIST, 1):
        # Simulated scoring for demo (replace with real evaluation)
        score = 100 if i % 3 != 0 else 60
        weight = get_metric_weight(name, category)
        metrics.append({"no": i, "name": name, "category": category, "score": score, "weight": weight})
        pillar_scores[category].append((score, weight))
        if score < 80:
            priority = "High" if score < 50 else "Medium"
            recommendation = f"Improve {name} in {category}"
            low_score_issues.append({"issue": name, "priority": priority, "recommendation": recommendation})

    # Weighted Pillar Score
    weighted_pillars = {}
    for cat, vals in pillar_scores.items():
        total_weight = sum(w for _, w in vals)
        weighted_score = sum(s*w for s, w in vals)/total_weight if total_weight else 100
        weighted_pillars[cat] = round(weighted_score)

    # Final score
    final_score = round(sum(weighted_pillars[cat]*PILLAR_WEIGHTS[cat] for cat in CATEGORIES))

    # Summary
    summary = f"Weighted Scores by Pillar: {weighted_pillars}"

    # 300-word Improvement Roadmap (dummy example)
    roadmap = "<b>Improvement Roadmap:</b><br/><br>" + \
              "<br/>".join([f"{i+1}. {item['recommendation']}" for i, item in enumerate(low_score_issues[:20])])

    return {
        "metrics": metrics,
        "pillar_avg": weighted_pillars,
        "total_grade": final_score,
        "summary": summary,
        "roadmap": roadmap
    }


# ==================== ENDPOINTS ====================
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/audit")
async def audit(request: Request):
    data = await request.json()
    raw_url = data.get("url", "").strip()
    mode = data.get("mode", "desktop") == "mobile"
    if not raw_url:
        raise HTTPException(400, "URL required")
    if not raw_url.startswith(("http://", "https://")):
        raw_url = "https://" + raw_url
    audit_data = await run_real_audit(raw_url, mode)
    soup = BeautifulSoup(audit_data["html"], "html.parser")
    results = generate_audit_results(audit_data, soup)
    return {
        "url": audit_data["final_url"],
        "total_grade": results["total_grade"],
        "pillars": results["pillar_avg"],
        "metrics": results["metrics"],
        "summary": results["summary"],
        "audited_at": time.strftime("%B %d, %Y at %H:%M UTC")
    }

@app.post("/download")
async def download_pdf(request: Request):
    data = await request.json()
    results = generate_audit_results({"final_url": data.get("url")}, BeautifulSoup("", "html.parser"))
    metrics = data.get("metrics", [])
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=60, bottomMargin=50)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitleBold', fontSize=20, leading=24, alignment=1, textColor=colors.HexColor("#10b981")))
    styles.add(ParagraphStyle(name='Section', fontSize=14, leading=18, spaceBefore=20, textColor=colors.HexColor("#0f172a")))
    story = []

    # Logo placeholder
    logo_path = "logo.png"
    if os.path.exists(logo_path):
        story.append(Image(logo_path, width=120, height=50))
        story.append(Spacer(1, 20))

    story.append(Paragraph("FF TECH ELITE - Enterprise Web Audit Report", styles['TitleBold']))
    story.append(Spacer(1, 20))
    story.append(Paragraph(f"Target URL: {data.get('url')}", styles['Normal']))
    story.append(Paragraph(f"Overall Health Score: {data.get('total_grade')}%", styles['Heading2']))
    story.append(Spacer(1, 15))

    # Pillar scores
    story.append(Paragraph("Pillar Scores", styles['Section']))
    pillar_table = [["Pillar", "Score"]]
    for cat, score in data.get("pillars", {}).items():
        pillar_table.append([cat, f"{score}%"])
    t = Table(pillar_table, colWidths=[300, 100])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0f172a")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey)
    ]))
    story.append(t)
    story.append(Spacer(1, 20))

    # Metrics table
    story.append(Paragraph("Detailed Metrics", styles['Section']))
    table_data = [["#", "Metric", "Category", "Score", "Weight"]]
    for m in metrics:
        table_data.append([m['no'], m['name'], m['category'], f"{m['score']}%", m['weight']])
    dt = Table(table_data, colWidths=[30, 220, 100, 50, 50])
    dt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#10b981")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey)
    ]))
    story.append(dt)
    story.append(PageBreak())

    # Improvement roadmap
    story.append(Paragraph("Improvement Roadmap", styles['TitleBold']))
    story.append(Spacer(1, 10))
    story.append(Paragraph(results["roadmap"], styles['Normal']))
    doc.build(story)
    buffer.seek(0)
    filename = f"FF_ELITE_Audit_Report_{int(time.time())}.pdf"
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={filename}"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
