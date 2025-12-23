import asyncio
import time
import io
import os
from typing import Dict, List, Tuple, Any
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from bs4 import BeautifulSoup

# ReportLab for stable PDF generation
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

app = FastAPI(title="FF TECH ELITE v2.0")

app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_methods=["*"], 
    allow_headers=["*"]
)

# Fixes the 404 by ensuring templates are loaded correctly
if not os.path.exists("templates"):
    os.makedirs("templates")
templates = Jinja2Templates(directory="templates")

# ==================== BROWSER ENGINE ====================
async def browser_audit(url: str, mobile: bool = False):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            viewport={"width": 390, "height": 844} if mobile else {"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        start_time = time.time()
        try:
            response = await page.goto(url, wait_until="load", timeout=60000)
            ttfb = (time.time() - start_time) * 1000
            
            perf = await page.evaluate("""
                () => {
                    const paints = performance.getEntriesByType('paint');
                    const lcp = performance.getEntriesByType('largest-contentful-paint');
                    return {
                        fcp: paints.find(p => p.name === 'first-contentful-paint')?.startTime || 0,
                        lcp: lcp.length ? lcp[lcp.length - 1].startTime : 0,
                        domCount: document.querySelectorAll('*').length
                    };
                }
            """)
            
            html = await page.content()
            await browser.close()
            return ttfb, perf, html
        except Exception as e:
            await browser.close()
            raise e

# ==================== ROUTES ====================

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serves the frontend and fixes the 404 error."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/audit")
async def audit(request: Request):
    data = await request.json()
    url = data.get("url", "").strip()
    if not url.startswith("http"): url = f"https://{url}"
    
    try:
        ttfb, perf, html = await browser_audit(url, data.get("mode") == "mobile")
        # Logic for grading and pillars goes here...
        return {
            "url": url,
            "total_grade": 85,  # Placeholder
            "pillars": {"Performance": 80, "SEO": 90, "UX": 85, "Security": 85},
            "summary": f"LCP {perf['lcp']:.0f}ms | FCP {perf['fcp']:.0f}ms",
            "metrics": [{"no": 1, "name": "LCP", "category": "Performance", "score": 90}]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/download")
async def download_pdf(request: Request):
    data = await request.json()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    content = [Paragraph(f"Audit Report: {data['url']}", getSampleStyleSheet()['Title'])]
    doc.build(content)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
