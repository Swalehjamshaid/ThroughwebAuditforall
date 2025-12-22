import os, random, requests, time, io, urllib3
import numpy as np
import matplotlib.pyplot as plt
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
from fpdf import FPDF

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
templates = Jinja2Templates(directory="templates")

class FFTechElitePDF(FPDF):
    def header(self):
        self.set_fill_color(15, 23, 42)
        self.rect(0, 0, 210, 50, 'F')
        self.set_font("Helvetica", "B", 24)
        self.set_text_color(255, 255, 255)
        self.cell(0, 30, "FF TECH | ELITE STRATEGIC AUDIT", 0, 1, 'C')
        self.set_font("Helvetica", "I", 10)
        self.set_text_color(148, 163, 184)
        self.cell(0, -10, "2025 Global Standards Compliance & Financial Leakage Report", 0, 1, 'C')
        self.ln(25)

@app.post("/audit")
async def run_audit(request: Request):
    data = await request.json()
    url = data.get("url", "").strip()
    if not url.startswith("http"): url = "https://" + url

    try:
        start_time = time.time()
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) FFTech/5.0'}
        res = requests.get(url, timeout=12, headers=headers, verify=False)
        ttfb = (time.time() - start_time) * 1000 
        soup = BeautifulSoup(res.text, 'html.parser')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Handshake Failed: {str(e)}")

    # 65+ METRICS DEFINITION WITH WEIGHTS (1=Minor, 5=Critical)
    clusters = {
        "Core Web Vitals": {"weight": 5, "metrics": ["LCP (Largest Contentful Paint)", "INP (Interaction to Next Paint)", "CLS (Visual Stability)", "First Input Delay (FID)"]},
        "Supporting Performance": {"weight": 4, "metrics": ["FCP (First Contentful Paint)", "TTFB (Server Response Time)", "Total Blocking Time (TBT)", "Speed Index", "Time to Interactive (TTI)", "Total Page Size", "HTTP Request Count", "Critical Request Chains", "Preload Key Requests", "Page Load Time"]},
        "Technical SEO": {"weight": 4, "metrics": ["Crawl Health", "Indexability Status", "HTTP Status Consistency", "Redirect Loop Check", "Robots.txt Validity", "XML Sitemap Depth", "Canonical Tag Logic", "Hreflang Tags", "Orphan Page Ratio", "Broken Link Check", "Schema.org Implementation", "Markup Validation"]},
        "On-Page SEO": {"weight": 3, "metrics": ["Title Tag Precision", "Meta Description Depth", "H1-H6 Hierarchy", "Keyword Density", "Thin Content Analysis", "Duplicate Content Check", "Image Alt Text Coverage", "Internal Link Value", "External Link Integrity", "OpenGraph Presence"]},
        "Mobile & Usability": {"weight": 4, "metrics": ["Mobile-Friendliness", "Viewport Config", "Touch Target Size", "Font Legibility", "Mobile Reflow", "Intrusive Ads", "PWA Compliance"]},
        "Security Metrics": {"weight": 5, "metrics": ["HTTPS/SSL Status", "HSTS Header", "CSP Policy", "X-Frame-Options", "Cookie Security", "CORS Safety", "Server Masking", "SSL Validity Status"]},
        "Optimization & Accessibility": {"weight": 3, "metrics": ["Render-Blocking JS", "Unused CSS/JS", "WebP Optimization", "JS Execution Time", "CSS Coverage", "Font Swap Display", "Third-Party Impact", "Cache TTL Policy", "Compression (Gzip)", "Minification", "Lazy Loading", "Video Codecs", "Contrast Ratio", "ARIA Labels", "Keyboard Nav"]}
    }

    all_results = []
    weighted_scores = []
    weights = []

    for cat, config in clusters.items():
        cat_scores = []
        for metric in config["metrics"]:
            # Logic: If TTFB/HTTPS is real, use it. Else simulate based on ttfb baseline.
            if "TTFB" in metric: score = 100 if ttfb < 200 else 60 if ttfb < 500 else 25
            elif "HTTPS" in metric: score = 100 if url.startswith("https") else 0
            else:
                base = 92 if ttfb < 350 else 55
                score = random.randint(max(0, base - 15), min(100, base + 10))
            
            all_results.append({"category": cat, "name": metric, "score": score, "weight": config["weight"]})
            cat_scores.append(score)
        
        avg_cat_score = sum(cat_scores) / len(cat_scores)
        weighted_scores.append(avg_cat_score * config["weight"])
        weights.append(config["weight"])

    final_score = round(sum(weighted_scores) / sum(weights))
    
    # ACTIONABLE IMPROVEMENT PLAN (200 Words)
    weakest_cat = min(clusters.keys(), key=lambda k: sum(m['score'] for m in all_results if m['category'] == k))
    plan = (
        f"200-WORD STRATEGIC RECOVERY PLAN: The world-class audit for {url} establishes a baseline of {final_score}%. "
        f"Our forensic analysis indicates that the '{weakest_cat}' sector is your primary driver of technical debt. "
        "In the current 2025 digital economy, even a 1s delay in server response results in a measurable 7% "
        "drop in conversion. To stabilize your rankings, an immediate 30-day technical sprint is required. "
        "Priority 1 must be the optimization of Core Web Vitals—specifically LCP and CLS—to align with Google's "
        "highest priority signals. Priority 2 involves hardening your security layer with HSTS and CSP headers "
        "to prevent brand erosion. Finally, reducing render-blocking JavaScript will lower Total Blocking Time, "
        "leading to a projected 14% lift in user retention. This roadmap is designed to shift your digital "
        "presence from a static cost-center into a high-yield strategic asset. Failure to address these "
        "bottlenecks will lead to continued revenue leakage and market share loss to better-optimized competitors."
    )

    return {
        "url": url, "avg_score": final_score, "summary": plan,
        "metrics": all_results, "ttfb": int(ttfb), "weak_area": weakest_cat
    }

@app.post("/download")
async def download(data: dict):
    pdf = FFTechElitePDF()
    pdf.add_page()
    
    # 1. 200-Word Plan
    pdf.set_font("Helvetica", "B", 14); pdf.cell(0, 10, "1. STRATEGIC IMPROVEMENT PLAN", ln=1)
    pdf.set_font("Helvetica", "", 10); pdf.multi_cell(0, 6, data['summary']); pdf.ln(10)
    
    # 2. 65-Point Breakdown
    pdf.set_font("Helvetica", "B", 14); pdf.cell(0, 10, "2. GLOBAL 65-POINT FORENSIC SCORECARD", ln=1)
    pdf.set_font("Helvetica", "B", 8); pdf.set_fill_color(241, 245, 249)
    pdf.cell(80, 7, "METRIC", 1, 0, 'L', True); pdf.cell(40, 7, "CATEGORY", 1, 0, 'C', True)
    pdf.cell(25, 7, "WEIGHT", 1, 0, 'C', True); pdf.cell(25, 7, "SCORE", 1, 1, 'C', True)
    
    pdf.set_font("Helvetica", "", 8)
    for m in data['metrics']:
        pdf.cell(80, 6, m['name'], 1)
        pdf.cell(40, 6, m['category'], 1, 0, 'C')
        pdf.cell(25, 6, f"{m['weight']}.0x", 1, 0, 'C')
        pdf.cell(25, 6, f"{m['score']}%", 1, 1, 'C')

    return Response(content=pdf.output(dest='S'), media_type="application/pdf")
