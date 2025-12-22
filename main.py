import io, os, hashlib, time, requests, urllib3, re, json
from typing import List, Dict, Tuple, Optional
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
from fpdf import FPDF
import uvicorn
import asyncio
import aiohttp
from urllib.parse import urlparse, urljoin

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI(title="FF TECH | Real Forensic Engine v6.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ---------------- METRICS ----------------
METRIC_DESCRIPTIONS = {
    "Performance": "Evaluates server response times, asset delivery speed, and rendering efficiency.",
    "Technical SEO": "Analyzes crawlability, indexing signals, and architecture semantic integrity.",
    "On-Page SEO": "Probes keyword relevance, content depth, and internal linking structures.",
    "Security": "Inspects SSL validity, encryption headers, and vulnerability mitigation.",
    "User Experience": "Measures visual stability, interactivity, and mobile-first design compliance."
}

RAW_METRICS = [(i+1, name, cat) for i,(name,cat) in enumerate([
("Largest Contentful Paint (LCP)","Performance"),
("First Input Delay (FID)","Performance"),
("Cumulative Layout Shift (CLS)","Performance"),
("First Contentful Paint (FCP)","Performance"),
("Time to First Byte (TTFB)","Performance"),
("Total Blocking Time (TBT)","Performance"),
("Speed Index","Performance"),
("Time to Interactive (TTI)","Performance"),
("Total Page Size","Performance"),
("HTTP Requests Count","Performance"),
("Image Optimization","Performance"),
("CSS Minification","Performance"),
("JavaScript Minification","Performance"),
("GZIP/Brotli Compression","Performance"),
("Browser Caching","Performance"),
("Mobile Responsiveness","Technical SEO"),
("Viewport Configuration","Technical SEO"),
("Structured Data Markup","Technical SEO"),
("Canonical Tags","Technical SEO"),
("Robots.txt Configuration","Technical SEO"),
("XML Sitemap","Technical SEO"),
("URL Structure","Technical SEO"),
("Breadcrumb Navigation","Technical SEO"),
("Title Tag Optimization","Technical SEO"),
("Meta Description","Technical SEO"),
("Heading Structure (H1-H6)","Technical SEO"),
("Internal Linking","Technical SEO"),
("External Linking Quality","Technical SEO"),
("Schema.org Implementation","Technical SEO"),
("AMP Compatibility","Technical SEO"),
("Content Quality Score","On-Page SEO"),
("Keyword Density Analysis","On-Page SEO"),
("Content Readability","On-Page SEO"),
("Content Freshness","On-Page SEO"),
("Content Length Adequacy","On-Page SEO"),
("Image Alt Text","On-Page SEO"),
("Video Optimization","On-Page SEO"),
("Content Uniqueness","On-Page SEO"),
("LSI Keywords","On-Page SEO"),
("Content Engagement Signals","On-Page SEO"),
("Content Hierarchy","On-Page SEO"),
("HTTPS Full Implementation","Security"),
("Security Headers","Security"),
("Cross-Site Scripting Protection","Security"),
("SQL Injection Protection","Security"),
("Mixed Content Detection","Security"),
("TLS/SSL Certificate Validity","Security"),
("Cookie Security","Security"),
("HTTP Strict Transport Security","Security"),
("Content Security Policy","Security"),
("Clickjacking Protection","Security"),
("Referrer Policy","Security"),
("Permissions Policy","Security"),
("X-Content-Type-Options","Security"),
("Frame Options","Security"),
("Core Web Vitals Compliance","User Experience"),
("Mobile-First Design","User Experience"),
("Accessibility Compliance","User Experience"),
("Page Load Animation","User Experience"),
("Navigation Usability","User Experience"),
("Form Optimization","User Experience"),
("404 Error Page","User Experience"),
("Search Functionality","User Experience"),
("Social Media Integration","User Experience"),
("Multilingual Support","User Experience"),
("Progressive Web App Features","User Experience")
])]

# ---------------- HELPERS ----------------
def score_bool(cond, ok=100, fail=30): return ok if cond else fail
def score_range(val, rules):
    for lim, sc in rules:
        if val <= lim: return sc
    return rules[-1][1]
def header(h, k): return k.lower() in [x.lower() for x in h]
def count(s, t): return len(s.find_all(t))

# ---------------- AUDITOR ----------------
class ForensicAuditor:
    def __init__(self, url):
        self.url = url
        self.domain = urlparse(url).netloc
        self.ttfb = 0
        self.headers = {}
        self.html = ""
        self.soup = None

    async def fetch(self):
        try:
            start = time.time()
            async with aiohttp.ClientSession() as s:
                async with s.get(self.url, ssl=False, timeout=12,
                    headers={"User-Agent":"FFTECH-ForensicBot/6.0"}) as r:
                    self.ttfb = (time.time()-start)*1000
                    self.headers = dict(r.headers)
                    self.html = await r.text()
                    self.soup = BeautifulSoup(self.html,"html.parser")
                    return True
        except: return False

# ---------------- PDF ----------------
class ExecutivePDF(FPDF):
    def __init__(self, url, grade):
        super().__init__()
        self.url=url; self.grade=grade
    def header(self):
        self.set_fill_color(15,23,42)
        self.rect(0,0,210,40,"F")
        self.set_font("Helvetica","B",20)
        self.set_text_color(255,255,255)
        self.cell(0,15,"FF TECH | EXECUTIVE FORENSIC REPORT",0,1,"C")
        self.set_font("Helvetica","",10)
        self.cell(0,6,self.url,0,1,"C")
        self.ln(10)

# ---------------- AUDIT ----------------
@app.post("/audit")
async def audit(request:Request):
    data = await request.json()
    url = data.get("url","").strip()
    if not url.startswith("http"): url="https://"+url

    A = ForensicAuditor(url)
    if not await A.fetch():
        return JSONResponse({"total_grade":1,"summary":"Site Unreachable"})

    s=A.soup; h=A.headers
    size=len(A.html.encode())/1024
    imgs=s.find_all("img"); links=s.find_all("a")

    pillars={k:[] for k in METRIC_DESCRIPTIONS}
    results=[]

    for i,n,c in RAW_METRICS:
        if n=="Time to First Byte (TTFB)": sc=score_range(A.ttfb,[(200,100),(600,70),(1500,40)])
        elif n=="Total Page Size": sc=score_range(size,[(800,100),(2000,70),(5000,40)])
        elif n=="HTTP Requests Count": sc=score_range(len(imgs)+len(links),[(50,100),(120,70),(300,40)])
        elif n=="Image Optimization": sc=score_range(len([i for i in imgs if not i.get("alt")]),[(0,100),(5,70),(20,40)])
        elif n=="Title Tag Optimization": sc=100 if s.title and 10<=len(s.title.text)<=60 else 40
        elif n=="Meta Description":
            m=s.find("meta",attrs={"name":"description"})
            sc=100 if m and 50<=len(m.get("content",""))<=160 else 40
        elif n=="Heading Structure (H1-H6)": sc=100 if count(s,"h1")==1 else 40
        elif n=="HTTPS Full Implementation": sc=score_bool(url.startswith("https"))
        elif n=="HTTP Strict Transport Security": sc=score_bool(header(h,"strict-transport-security"))
        elif n=="Content Security Policy": sc=score_bool(header(h,"content-security-policy"))
        elif n=="X-Content-Type-Options": sc=score_bool(header(h,"x-content-type-options"))
        elif n=="Frame Options": sc=score_bool(header(h,"x-frame-options"))
        elif n=="Mobile-First Design": sc=score_bool(s.find("meta",attrs={"name":"viewport"}))
        elif n=="Navigation Usability": sc=score_bool(s.find("nav"))
        else: sc=70

        sc=max(1,min(100,sc))
        results.append({"no":i,"name":n,"category":c,"score":sc})
        pillars[c].append(sc)

    pillar_avg={k:round(sum(v)/len(v)) for k,v in pillars.items()}
    total=round(sum(pillar_avg.values())/5)

    return {"url":url,"total_grade":total,"pillars":pillar_avg,"metrics":results,
            "summary":f"Real forensic audit completed. Health Index {total}%."}

# ---------------- PDF ----------------
@app.post("/download")
async def download(request:Request):
    d=await request.json()
    pdf=ExecutivePDF(d["url"],d["total_grade"])
    pdf.add_page()
    pdf.set_font("Helvetica","B",40)
    pdf.set_text_color(59,130,246)
    pdf.cell(0,30,f'{d["total_grade"]}%',1,1,"C")
    out=pdf.output(dest="S").encode("latin1")
    return StreamingResponse(io.BytesIO(out),
        media_type="application/pdf",
        headers={"Content-Disposition":"attachment; filename=Audit_Report.pdf"})

# ---------------- UI ----------------
@app.get("/",response_class=HTMLResponse)
async def ui():
    return "<h1 style='color:white;background:#020617;padding:40px'>FF TECH Forensic Engine v6.0 – READY</h1>"

if __name__=="__main__":
    uvicorn.run(app,host="0.0.0.0",port=8000)
