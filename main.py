import io, os, hashlib, time, random, urllib3, json
from typing import List, Dict, Tuple, Optional
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
from fpdf import FPDF
import uvicorn
import aiohttp
from urllib.parse import urlparse

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI(title="FF TECH | Real Forensic Engine v6.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Remediation Database for the PDF
REMEDIATION_GUIDE = {
    "Performance": "Optimize server-side caching and implement a global CDN to reduce latency.",
    "Technical SEO": "Correct robots.txt directives and ensure XML sitemap is submitted to Search Console.",
    "On-Page SEO": "Increase keyword semantic density and fix heading hierarchy (H1-H6).",
    "Security": "Hardening required: Implement HSTS headers and update TLS to version 1.3.",
    "User Experience": "Improve Core Web Vitals by deferring non-critical JS and fixing layout shifts."
}

RAW_METRICS = [
    (1, "Largest Contentful Paint (LCP)", "Performance"), (2, "First Input Delay (FID)", "Performance"),
    (3, "Cumulative Layout Shift (CLS)", "Performance"), (4, "First Contentful Paint (FCP)", "Performance"),
    (5, "Time to First Byte (TTFB)", "Performance"), (6, "Total Blocking Time (TBT)", "Performance"),
    (7, "Speed Index", "Performance"), (8, "Time to Interactive (TTI)", "Performance"),
    (9, "Total Page Size", "Performance"), (10, "HTTP Requests Count", "Performance"),
    (11, "Image Optimization", "Performance"), (12, "CSS Minification", "Performance"),
    (13, "JavaScript Minification", "Performance"), (14, "GZIP/Brotli Compression", "Performance"),
    (15, "Browser Caching", "Performance"), (16, "Mobile Responsiveness", "Technical SEO"),
    (17, "Viewport Configuration", "Technical SEO"), (18, "Structured Data Markup", "Technical SEO"),
    (19, "Canonical Tags", "Technical SEO"), (20, "Robots.txt Configuration", "Technical SEO"),
    (21, "XML Sitemap", "Technical SEO"), (22, "URL Structure", "Technical SEO"),
    (23, "Breadcrumb Navigation", "Technical SEO"), (24, "Title Tag Optimization", "Technical SEO"),
    (25, "Meta Description", "Technical SEO"), (26, "Heading Structure (H1-H6)", "Technical SEO"),
    (27, "Internal Linking", "Technical SEO"), (28, "External Linking Quality", "Technical SEO"),
    (29, "Schema.org Implementation", "Technical SEO"), (30, "AMP Compatibility", "Technical SEO"),
    (31, "Content Quality Score", "On-Page SEO"), (32, "Keyword Density Analysis", "On-Page SEO"),
    (33, "Content Readability", "On-Page SEO"), (34, "Content Freshness", "On-Page SEO"),
    (35, "Content Length Adequacy", "On-Page SEO"), (36, "Image Alt Text", "On-Page SEO"),
    (37, "Video Optimization", "On-Page SEO"), (38, "Content Uniqueness", "On-Page SEO"),
    (39, "LSI Keywords", "On-Page SEO"), (40, "Content Engagement Signals", "On-Page SEO"),
    (41, "Content Hierarchy", "On-Page SEO"), (42, "HTTPS Full Implementation", "Security"),
    (43, "Security Headers", "Security"), (44, "Cross-Site Scripting Protection", "Security"),
    (45, "SQL Injection Protection", "Security"), (46, "Mixed Content Detection", "Security"),
    (47, "TLS/SSL Certificate Validity", "Security"), (48, "Cookie Security", "Security"),
    (49, "HTTP Strict Transport Security", "Security"), (50, "Content Security Policy", "Security"),
    (51, "Clickjacking Protection", "Security"), (52, "Referrer Policy", "Security"),
    (53, "Permissions Policy", "Security"), (54, "X-Content-Type-Options", "Security"),
    (55, "Frame Options", "Security"), (56, "Core Web Vitals Compliance", "User Experience"),
    (57, "Mobile-First Design", "User Experience"), (58, "Accessibility Compliance", "User Experience"),
    (59, "Page Load Animation", "User Experience"), (60, "Navigation Usability", "User Experience"),
    (61, "Form Optimization", "User Experience"), (62, "404 Error Page", "User Experience"),
    (63, "Search Functionality", "User Experience"), (64, "Social Media Integration", "User Experience"),
    (65, "Multilingual Support", "User Experience"), (66, "Progressive Web App Features", "User Experience")
]

class ExecutivePDF(FPDF):
    def __init__(self, url, grade):
        super().__init__(orientation='L', unit='mm', format='A4') # Landscape for more detail
        self.target_url = url
        self.grade = grade

    def header(self):
        self.set_fill_color(15, 23, 42)
        self.rect(0, 0, 297, 40, 'F')
        self.set_font("Helvetica", "B", 20)
        self.set_text_color(255, 255, 255)
        self.cell(0, 15, "FF TECH | ELITE FORENSIC REMEDIATION REPORT", 0, 1, 'C')
        self.set_font("Helvetica", "", 9)
        self.cell(0, 5, f"TARGET: {self.target_url}  |  HEALTH INDEX: {self.grade}%", 0, 1, 'C')
        self.ln(10)

@app.post("/download")
async def download_pdf(request: Request):
    data = await request.json()
    pdf = ExecutivePDF(data['url'], data['total_grade'])
    pdf.add_page()
    
    # Header for the Matrix
    pdf.set_fill_color(30, 41, 59)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(10, 10, "ID", 1, 0, 'C', True)
    pdf.cell(60, 10, "FORENSIC METRIC", 1, 0, 'L', True)
    pdf.cell(30, 10, "CATEGORY", 1, 0, 'L', True)
    pdf.cell(20, 10, "SCORE", 1, 0, 'C', True)
    pdf.cell(157, 10, "ACTIONABLE REMEDIATION / FIX", 1, 1, 'L', True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 7)
    
    for i, m in enumerate(data['metrics']):
        if pdf.get_y() > 180: pdf.add_page() # Page break for landscape
        bg = (i % 2 == 0)
        if bg: pdf.set_fill_color(248, 250, 252)
        
        # Determine remediation text
        fix_text = REMEDIATION_GUIDE.get(m['category'], "Verify technical implementation.")
        if m['score'] > 90: fix_text = "Optimized. Maintain current configuration."
        
        pdf.cell(10, 7, str(m['no']), 1, 0, 'C', bg)
        pdf.cell(60, 7, m['name'][:40], 1, 0, 'L', bg)
        pdf.cell(30, 7, m['category'], 1, 0, 'L', bg)
        
        # Color score
        if m['score'] > 85: pdf.set_text_color(22, 163, 74)
        elif m['score'] < 50: pdf.set_text_color(220, 38, 38)
        else: pdf.set_text_color(202, 138, 4)
        
        pdf.cell(20, 7, f"{m['score']}%", 1, 0, 'C', bg)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(157, 7, fix_text, 1, 1, 'L', bg)

    buf = io.BytesIO()
    pdf_out = pdf.output(dest='S')
    buf.write(pdf_out if isinstance(pdf_out, bytes) else pdf_out.encode('latin-1'))
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf")

# ... (rest of the FastAPI /audit and index endpoints)
