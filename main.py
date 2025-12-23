import time, io, json, math, re, os, asyncio
from urllib.parse import urlparse
from typing import Dict, List, Any

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright

# reportlab is more robust for production PDF generation
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

app = FastAPI(title="FF TECH ELITE – Real-Time Enterprise Auditor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== HELPERS ====================

def normalize_url(url: str) -> str:
    if not url.startswith("http"):
        return f"https://{url}"
    return url

def clamp(v: float) -> int:
    return max(0, min(100, int(v)))

# ==================== AUDIT ENGINE ====================

async def run_audit(url: str, mode: str):
    metrics = []
    issues = []
    
    async with async_playwright() as p:
        # Launching with stealth-like args to avoid bot detection
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(
            viewport={"width": 375, "height": 812} if mode == "mobile" else {"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        start_time = time.time()
        try:
            # Combined network idle and load for accuracy
            response = await page.goto(url, wait_until="networkidle", timeout=45000)
            ttfb = (time.time() - start_time) * 1000
            
            # 1. Performance - Native Playwright CDPSession (No subprocess required)
            client = await page.context.new_cdp_session(page)
            await client.send("Performance.enable")
            perf_metrics = await client.send("Performance.getMetrics")
            
            # Extract basic JS performance metrics
            js_metrics = await page.evaluate("""() => {
                const paints = performance.getEntriesByType('paint');
                const fcp = paints.find(p => p.name === 'first-contentful-paint')?.startTime || 0;
                const lcp = performance.getEntriesByType('largest-contentful-paint').pop()?.startTime || 0;
                return { fcp, lcp, domCount: document.querySelectorAll('*').length };
            }""")

            html = await page.content()
            headers = response.headers
            status = response.status

            # 2. Async check for SEO files (robots/sitemap)
            async with httpx.AsyncClient(timeout=5.0) as client_http:
                parsed = urlparse(url)
                base = f"{parsed.scheme}://{parsed.netloc}"
                robots_req = await client_http.get(f"{base}/robots.txt")
                sitemap_req = await client_http.get(f"{base}/sitemap.xml")

        except Exception as e:
            await browser.close()
            raise HTTPException(status_code=500, detail=f"Audit failed: {str(e)}")
        
        await browser.close()

    soup = BeautifulSoup(html, "html.parser")

    # ==================== SCORING LOGIC ====================

    # Performance Pillar
    lcp_score = clamp(100 - (js_metrics['lcp'] / 40))
    fcp_score = clamp(100 - (js_metrics['fcp'] / 30))
    metrics.append({"name": "Largest Contentful Paint", "category": "Performance", "score": lcp_score})
    metrics.append({"name": "First Contentful Paint", "category": "Performance", "score": fcp_score})

    # SEO Pillar
    seo_title = soup.title and 15 <= len(soup.title.text) <= 65
    metrics.append({"name": "Title Optimization", "category": "SEO", "score": 100 if seo_title else 0})
    if not seo_title:
        issues.append({"type": "SEO", "issue": "Title Tag length invalid", "fix": "Set title between 15-65 chars."})

    robots_ok = robots_req.status_code == 200
    metrics.append({"name": "Robots.txt", "category": "SEO", "score": 100 if robots_ok else 0})

    # Security Pillar
    hsts = "strict-transport-security" in headers
    csp = "content-security-policy" in headers
    sec_score = sum([20 if hsts else 0, 30 if csp else 0, 50 if url.startswith("https") else 0])
    metrics.append({"name": "Security Headers", "category": "Security", "score": sec_score})

    # Final Calculation
    pillars = {
        "Performance": round((lcp_score + fcp_score) / 2),
        "SEO": 100 if robots_ok and seo_title else 50,
        "Security": sec_score,
        "UX": clamp(100 - (js_metrics['domCount'] / 20))
    }
    
    return {
        "url": url,
        "total_grade": round(sum(pillars.values()) / len(pillars)),
        "pillars": pillars,
        "metrics": metrics,
        "issues": issues,
        "audited_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

# ==================== ENDPOINTS ====================

@app.post("/audit")
async def audit_endpoint(req: Request):
    body = await req.json()
    url = normalize_url(body["url"])
    return await run_audit(url, body.get("mode", "desktop"))

@app.post("/download")
async def download_pdf(data: dict):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # Report Header
    elements.append(Paragraph(f"<b>FF TECH ELITE Audit: {data['url']}</b>", styles['Title']))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Overall Grade: {data['total_grade']}%", styles['Heading2']))
    elements.append(Spacer(1, 12))

    # Issues Table
    if data.get("issues"):
        elements.append(Paragraph("Priority Issues:", styles['Heading3']))
        table_data = [["Type", "Issue", "Recommended Fix"]]
        for iss in data['issues']:
            table_data.append([iss['type'], iss['issue'], iss['fix']])
        
        t = Table(table_data, colWidths=[80, 150, 250])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTSIZE', (0,0), (-1,-1), 9)
        ]))
        elements.append(t)

    doc.build(elements)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=audit_{int(time.time())}.pdf"
    })
