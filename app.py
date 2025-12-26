
"""
FF Tech – AI-Powered Website Audit & Compliance SaaS
Single-file FastAPI backend, Railway-ready, integrated with your advanced HTML.

Fixes in this version:
- Root route (/) now always attempts to render the latest audit dashboard.
- Optional auto-seed on startup using env AUTO_SEED_AUDIT_URL if no audits exist.
- Safe fallback to styled status page when DB is unreachable or data is empty.
- Auto-migration of missing columns in Postgres (RBAC/2FA + template extras).
- Inline rendering of your provided HTML (uses templates/index.html if present).
"""

import os
import hmac
import json
import base64
import time
import smtplib
import ssl as sslmod
import socket
import hashlib
import secrets
import datetime as dt
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

# FastAPI & deps
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
import jwt

# DB
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey,
    Text, Float, JSON, func, text
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
from sqlalchemy.exc import SQLAlchemyError

# HTTP, parsing
import requests
from bs4 import BeautifulSoup

# Scheduler (optional use)
from apscheduler.schedulers.background import BackgroundScheduler

# PDF reporting
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

# -----------------------------------------------------------------------------
# Config (Railway-friendly via env vars)
# -----------------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "change_me_dev_only")
APP_DOMAIN = os.getenv("APP_DOMAIN", "http://localhost:8000")
ENV = os.getenv("ENV", "development")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fftech.db")
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Asia/Karachi")
FFTECH_LOGO_TEXT = os.getenv("FFTECH_LOGO_TEXT", "FF Tech")
FFTECH_CERT_STAMP_TEXT = os.getenv("FFTECH_CERT_STAMP_TEXT", "Certified Audit Report")

# Optional: auto-seed first audit at startup if none exist
AUTO_SEED_AUDIT_URL = os.getenv("AUTO_SEED_AUDIT_URL", "").strip()

# -----------------------------------------------------------------------------
# App & Templates
# -----------------------------------------------------------------------------
app = FastAPI(title="FF Tech Website Audit SaaS", version="1.0.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if ENV != "production" else [APP_DOMAIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates_dir = Path("templates")
templates = Jinja2Templates(directory=str(templates_dir)) if templates_dir.exists() else None

# -----------------------------------------------------------------------------
# Inline HTML (your provided advanced template)
# -----------------------------------------------------------------------------
INLINE_HTML = r"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
<meta charset="UTF-8">
<title>FF Tech AI Website Audit | {{ audit.website.url }}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">

<!-- Tailwind CSS -->
<script/cdn.tailwindcss.com</script>
<!-- Chart.js -->
https://cdn.jsdelivr.net/npm/chart.js</script>
<!-- Google Fonts -->
https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800;900&display=swap

<style>
body { font-family: Inter, system-ui; transition: background 0.3s, color 0.3s; }
.glass { background: rgba(15,23,42,.65); backdrop-filter: blur(16px); border: 1px solid rgba(255,255,255,.08); transition: transform 0.3s; }
.glass:hover { transform: translateY(-5px); }
.glow { box-shadow: 0 0 40px rgba(99,102,241,.25); }
.pulse { animation: pulse 2s infinite; }
@keyframes pulse { 0%{opacity:.4}50%{opacity:1}100%{opacity:.4} }
.severity-high { color: #ef4444; font-weight: 700; }
.severity-medium { color: #f59e0b; font-weight: 700; }
.severity-low { color: #38bdf8; font-weight: 700; }
.collapsible { cursor: pointer; }
.content { max-height: 0; overflow: hidden; transition: max-height 0.3s ease; }
.tooltip { position: relative; display: inline-block; }
.tooltip .tooltiptext { visibility: hidden; width: 220px; background-color: #111827; color: #fff; text-align: center; border-radius: 6px; padding: 5px; position: absolute; z-index: 10; bottom: 125%; left: 50%; margin-left: -110px; opacity: 0; transition: opacity 0.3s; font-size: 12px; }
.tooltip:hover .tooltiptext { visibility: visible; opacity: 1; }
.tab-button { padding:0.5rem 1rem; border-radius: 0.5rem; font-weight:600; transition: all 0.3s; }
.tab-button.active { background-color: #6366f1; color:white; }
.progress-bar { background: linear-gradient(90deg, #6366f1, #4f46e5); height: 8px; border-radius: 4px; transition: width 0.5s ease-in-out; }
.fadeIn { animation: fadeIn 0.8s ease-in-out; }
</style>
</head>
<body class="bg-slate-950 text-slate-200 min-h-screen">

<header class="border-b border-white/10">
<div class="max-w-7xl mx-auto px-6 py-6 flex justify-between items-center">
  <div>
    <h1 class="text-3xl font-black">FF TECH <span class="text-indigo-400">AI AUDIT</span></h1>
    <p class="text-sm text-slate-400">{{ audit.website.url }}</p>
  </div>
  <div class="flex items-center gap-4">
    <button onclick="toggleMode()" class="px-3 py-1 bg-indigo-500/20 text-indigo-400 rounded-full text-sm font-bold">Toggle Dark/Light</button>
    <button onclick="downloadPDF()" class="px-3 py-1 bg-emerald-500/20 text-emerald-400 rounded-full text-sm font-bold">Download PDF</button>
  </div>
</div>
</header>

<div class="max-w-7xl mx-auto px-6 py-2">
  <div id="liveBanner" class="bg-indigo-600/20 text-indigo-400 rounded-full px-4 py-2 font-bold flex items-center gap-2">
    <span>Audit in Progress</span>
    <span class="animate-pulse">●</span>
  </div>
</div>

<div class="max-w-7xl mx-auto px-6 py-6">
  <div class="flex gap-4 flex-wrap">
    <button class="tab-button active" onclick="showTab('overview')">Overview</button>
    <button class="tab-button" onclick="showTab('seo')">SEO</button>
    <button class="tab-button" onclick="showTab('performance')">Performance</button>
    <button class="tab-button" onclick="showTab('security')">Security</button>
    <button class="tab-button" onclick="showTab('compliance')">Compliance</button>
    <button class="tab-button" onclick="showTab('recommendations')">Recommendations</button>
  </div>
</div>

<div class="max-w-7xl mx-auto px-6">
  <div id="overview" class="tab-content fadeIn">
    <section class="grid lg:grid-cols-3 gap-8 py-6">
      <div class="glass glow rounded-3xl p-8 text-center">
        <p class="text-slate-400">Site Health Score</p>
        <p class="text-7xl font-black text-indigo-400 mt-2" id="siteScore">{{ audit.site_health_score }}%</p>
        <p class="mt-4 text-sm">Grade: <span class="font-bold text-emerald-400" id="siteGrade">{{ audit.grade }}</span></p>
        <p class="mt-2 text-xs text-slate-400">Compared to last audit: {{ previous_audit.site_health_score if previous_audit else audit.site_health_score }}%</p>
      </div>
      <div class="glass rounded-3xl p-8 col-span-2">
        <h2 class="text-xl font-bold mb-4">Audit Timeline</h2>
        <div class="space-y-4" id="auditTimeline">
          {% for step in ["Crawling","SEO Analysis","Performance","Security","Compliance","Scoring"] %}
          <div class="flex items-center gap-4">
            <div class="w-6 h-6 rounded-full border-2 border-indigo-400 flex items-center justify-center">
              <span class="w-3 h-3 bg-emerald-400 rounded-full pulse" id="pulse-{{ loop.index }}"></span>
            </div>
            <div class="flex-1">
              <p class="font-semibold">{{ step }}</p>
              <div class="w-full bg-slate-800 rounded h-2 mt-1">
                <div class="progress-bar" style="width:0%" id="progress-{{ loop.index }}"></div>
              </div>
            </div>
          </div>
          {% endfor %}
        </div>
      </div>
    </section>

    <section class="grid lg:grid-cols-2 gap-8 py-6">
      <div class="glass rounded-3xl p-8">
        <h2 class="text-xl font-bold mb-4">Issue Distribution</h2>
        <canvas id="issuesChart"></canvas>
      </div>
      <div class="glass rounded-3xl p-8">
        <h2 class="text-xl font-bold mb-4">Health Trend</h2>
        <canvas id="trendChart"></canvas>
      </div>
    </section>

    <section class="py-6">
      <div class="glass rounded-3xl p-8">
        <h2 class="text-2xl font-extrabold mb-6">Competitor Comparison</h2>
        <div class="grid md:grid-cols-3 gap-6 text-center">
          <div class="p-6 bg-slate-900 rounded-xl">
            <p class="text-sm text-slate-400">Your Website</p>
            <p class="text-4xl font-black text-indigo-400">{{ audit.site_health_score }}%</p>
            <div class="h-2 bg-indigo-400 rounded mt-2" style="width:{{ audit.site_health_score }}%"></div>
          </div>
          {% for comp in audit.competitors %}
          <div class="p-6 bg-slate-900 rounded-xl opacity-70">
            <p class="text-sm text-slate-400">{{ comp.name }}</p>
            <p class="text-4xl font-black">{{ comp.score }}%</p>
            <div class="h-2 bg-gray-500 rounded mt-2" style="width:{{ comp.score }}%"></div>
          </div>
          {% endfor %}
        </div>
      </div>
    </section>

    <section class="py-6">
      <div class="glass rounded-3xl p-8">
        <h2 class="text-2xl font-extrabold mb-4">Top 10 Issues</h2>
        <table class="w-full text-left border-collapse text-sm">
          <thead>
            <tr class="border-b border-slate-700">
              <th class="py-2 px-4">Issue</th>
              <th class="py-2 px-4">Severity</th>
              <th class="py-2 px-4">Suggestion</th>
            </tr>
          </thead>
          <tbody>
            {% for issue in audit.top_issues %}
            <tr class="border-b border-slate-800 hover:bg-slate-800 transition">
              <td class="py-2 px-4">{{ issue.name }}</td>
              <td class="py-2 px-4">
                <span class="severity-{{ issue.severity }}">{{ issue.severity|capitalize }}</span>
              </td>
              <td class="py-2 px-4">{{ issue.suggestion }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </section>

    <section class="py-6 grid md:grid-cols-2 xl:grid-cols-3 gap-6">
      {% for k,v in audit.metrics_summary.items() %}
      <div class="glass rounded-2xl p-6 tooltip" data-value="{{ v }}" data-key="{{ k }}">
        <p class="text-xs text-slate-400 uppercase">{{ k.replace("_"," ") }}</p>
        <p class="text-2xl font-bold mt-2">{{ v }}</p>
        <span class="tooltiptext">{{ audit.recommendations.get(k, "No recommendation available") }}</span>
      </div>
      {% endfor %}
    </section>

    <section class="py-6">
      <div class="glass rounded-3xl p-8 border border-red-500/30">
        <h2 class="text-2xl font-extrabold mb-6 text-red-400 collapsible" onclick="toggleContent('weaknessesContent')">Priority Weak Areas</h2>
        <ul class="space-y-3 content" id="weaknessesContent">
          {% for w in audit.weaknesses %}
          <li class="flex gap-3"><span class="text-red-500">●</span><span>{{ w }}</span></li>
          {% endfor %}
        </ul>
      </div>
    </section>
  </div>
</div>

<footer class="border-t border-white/10 mt-20">
<div class="max-w-7xl mx-auto px-6 py-8 text-center text-sm text-slate-500">
FF Tech © AI Website Audit Platform · Generated {{ audit.finished_at }}
</div>
</footer>

<script>
function showTab(tabId){
  document.querySelectorAll('.tab-content').forEach(tab => tab.classList.add('hidden'));
  document.getElementById(tabId).classList.remove('hidden');
  document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
  event.currentTarget.classList.add('active');
}
function toggleMode() {
  document.documentElement.classList.toggle('dark');
  document.body.classList.toggle('bg-slate-50');
  document.body.classList.toggle('text-slate-900');
}
function toggleContent(id) {
  const el = document.getElementById(id);
  el.style.maxHeight = el.style.maxHeight === '0px' || !el.style.maxHeight ? el.scrollHeight + 'px' : '0px';
}
function downloadPDF() { alert("PDF export integration coming soon."); }
let currentStep = 1;
function animateAudit() {
  const steps = ["Crawling","SEO Analysis","Performance","Security","Compliance","Scoring"];
  if(currentStep > steps.length) return;
  const bar = document.getElementById('progress-' + currentStep);
  let width = 0;
  const interval = setInterval(() => {
    if(width >= (currentStep*16)) clearInterval(interval);
    bar.style.width = width + '%';
    width++;
  }, 20);
  currentStep++;
  setTimeout(animateAudit, 800);
}
animateAudit();

new Chart(document.getElementById("issuesChart"), {
  type: "doughnut",
  data: {
    labels: ["Errors","Warnings","Notices"],
    datasets: [{data:[{{ audit.metrics_summary.total_errors }},{{ audit.metrics_summary.total_warnings }},{{ audit.metrics_summary.total_notices }}],backgroundColor:["#ef4444","#f59e0b","#38bdf8"]}]
  },
  options:{plugins:{legend:{labels:{color:"#cbd5f5"}}}}
});

new Chart(document.getElementById("trendChart"), {
  type:"line",
  data:{labels:["Previous","Current"],datasets:[{data:[{{ previous_audit.site_health_score if previous_audit else audit.site_health_score }},{{ audit.site_health_score }}],borderColor:"#6366f1",backgroundColor:"rgba(99,102,241,.2)",tension:.4,fill:true,pointRadius:6}]},
  options:{scales:{x:{ticks:{color:"#cbd5f5"}},y:{ticks:{color:"#cbd5f5"},min:0,max:100}},plugins:{legend:{display:false}}}
});
</script>
</body>
</html>
"""

# -----------------------------------------------------------------------------
# DB setup (hardened)
# -----------------------------------------------------------------------------
Base = declarative_base()
try:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
except Exception:
    engine = create_engine("sqlite:///./fftech.db", pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# -----------------------------------------------------------------------------
# Models (minimal set required by template & routes)
# -----------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=False)
    role = Column(String, default="user")                   # RBAC
    totp_enabled = Column(Boolean, default=False)           # 2FA flag
    totp_secret = Column(String, nullable=True)             # base32 secret
    created_at = Column(DateTime, default=func.now())
    timezone = Column(String, default=DEFAULT_TIMEZONE)


class LoginActivity(Base):
    __tablename__ = "login_activities"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    ip = Column(String)
    user_agent = Column(String)
    success = Column(Boolean, default=True)
    reason = Column(String, nullable=True)
    timestamp = Column(DateTime, default=func.now())


class Website(Base):
    __tablename__ = "websites"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    url = Column(String, index=True)
    created_at = Column(DateTime, default=func.now())
    is_active = Column(Boolean, default=True)


class AuditRun(Base):
    __tablename__ = "audit_runs"
    id = Column(Integer, primary_key=True)
    website_id = Column(Integer, ForeignKey("websites.id"))
    started_at = Column(DateTime, default=func.now())
    finished_at = Column(DateTime)
    site_health_score = Column(Float)          # 0-100
    grade = Column(String)                     # A+, A, B, C, D
    metrics_summary = Column(JSON)             # dict of metrics -> values
    weaknesses = Column(JSON)                  # list of weaknesses
    executive_summary = Column(Text)           # ~200 words
    # Optional fields used by your template:
    competitors = Column(JSON, nullable=True)  # [{name, score}]
    top_issues = Column(JSON, nullable=True)   # [{name, severity, suggestion}]
    recommendations = Column(JSON, nullable=True)  # {metric_key: suggestion}

# -----------------------------------------------------------------------------
# Schemas
# -----------------------------------------------------------------------------
class AuditStartRequest(BaseModel):
    website_url: str = Field(..., description="URL to audit")

# -----------------------------------------------------------------------------
# Helpers (security, email)
# -----------------------------------------------------------------------------
bearer = HTTPBearer()

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_000)
    return f"pbkdf2$sha256$100000${salt}${base64.b64encode(dk).decode()}"

def send_email(to_email: str, subject: str, html_body: str, plain_body: str = ""):
    # optional SMTP integration; omitted here for simplicity
    pass

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------------------------------------------------------------
# Audit Engine (core checks + strict scoring)
# -----------------------------------------------------------------------------
def fetch(url: str, timeout: int = 20) -> Tuple[int, str, Dict[str, str], float]:
    start = time.time()
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "FFTechAudit/1.0"})
        ttfb = r.elapsed.total_seconds() if hasattr(r, "elapsed") else (time.time() - start)
        return r.status_code, r.text or "", dict(r.headers), ttfb
    except requests.RequestException:
        return 0, "", {}, 0.0

def resolve_ssl(hostname: str, port: int = 443) -> Dict[str, Any]:
    out = {"valid": False, "notBefore": None, "notAfter": None, "error": None}
    try:
        ctx = sslmod.create_default_context()
        with socket.create_connection((hostname, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercertificate()
                out["notBefore"] = cert.get("notBefore")
                out["notAfter"] = cert.get("notAfter")
                out["valid"] = True
    except Exception as e:
        out["error"] = str(e)
    return out

def normalize_url(u: str) -> str:
    return u.strip()

def extract_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc
    except Exception:
        return ""

def parse_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")

def count_text_words(soup: BeautifulSoup) -> int:
    text = soup.get_text(separator=" ")
    return len([w for w in text.split() if w.strip()])

def is_https(url: str) -> bool:
    return url.lower().startswith("https://")

def check_security_headers(headers: Dict[str, str]) -> Dict[str, bool]:
    keys = ["content-security-policy", "strict-transport-security", "x-frame-options"]
    hdrs = {k.lower(): True for k in headers.keys()}
    return {k: (k in hdrs) for k in keys}

def sizeof_response(headers: Dict[str, str], body: str) -> int:
    cl = headers.get("Content-Length") or headers.get("content-length")
    if cl and str(cl).isdigit():
        return int(cl)
    return len(body.encode())

def find_links(soup: BeautifulSoup, base_url: str) -> Dict[str, List[str]]:
    anchors, imgs, css, js = [], [], [], []
    from urllib.parse import urljoin
    for a in soup.find_all("a"):
        href = a.get("href")
        if href:
            anchors.append(urljoin(base_url, href))
    for i in soup.find_all("img"):
        src = i.get("src")
        if src:
            imgs.append(urljoin(base_url, src))
    for l in soup.find_all("link", rel=lambda x: x in ["stylesheet", "preload"] if x else False):
        href = l.get("href")
        if href:
            css.append(urljoin(base_url, href))
    for s in soup.find_all("script"):
        src = s.get("src")
        if src:
            js.append(urljoin(base_url, src))
    return {"anchors": anchors, "images": imgs, "css": css, "js": js}

def check_broken_links(urls: List[str], limit: int = 100) -> Dict[str, Any]:
    broken, redirected = [], []
    for u in urls[:limit]:
        try:
            r = requests.head(u, allow_redirects=True, timeout=10, headers={"User-Agent": "FFTechAudit/1.0"})
            if 400 <= r.status_code < 600:
                broken.append(u)
            elif len(r.history) > 0:
                redirected.append(u)
        except Exception:
            broken.append(u)
    return {"broken": broken, "redirected": redirected, "tested": min(limit, len(urls))}

def check_robot_sitemap(base_url: str) -> Dict[str, Any]:
    from urllib.parse import urlparse, urljoin
    p = urlparse(base_url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    sitemap = None
    robots_status, robots_text, _, _ = fetch(robots_url)
    if robots_status == 200 and robots_text:
        for line in robots_text.splitlines():
            if line.lower().startswith("sitemap:"):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    sitemap = parts[1].strip()
    if not sitemap:
        sitemap = urljoin(base_url, "/sitemap.xml")
    sm_status, sm_text, _, _ = fetch(sitemap)
    return {
        "robots_found": robots_status == 200,
        "sitemap_url": sitemap,
        "sitemap_status": sm_status,
        "sitemap_size_bytes": len(sm_text.encode()) if sm_text else 0
    }

def grade_from_score(score: float) -> str:
    if score >= 95: return "A+"
    if score >= 85: return "A"
    if score >= 75: return "B"
    if score >= 65: return "C"
    return "D"

def generate_summary(website_url: str, metrics: Dict[str, Any], weaknesses: List[str]) -> str:
    score = metrics.get("site_health_score", 0)
    grade = metrics.get("grade", "N/A")
    weak_list = ", ".join(weaknesses[:6]) if weaknesses else "No critical weaknesses detected"
    words = [
        f"FF Tech Audit Summary for {website_url}:",
        f"The website achieved a health score of {int(score)}% and an overall grade of {grade}.",
        "Our comprehensive audit examined technical SEO, crawlability, on-page content, performance,"
        " mobile usability, and security. The site demonstrates strengths in core availability and"
        " basic meta tag hygiene; however, opportunities exist to improve both resiliency and search visibility.",
        "Key areas identified for improvement include: " + weak_list + ". Addressing these items will reduce risk,"
        " enhance crawl efficiency, and improve user experience across devices.",
        "Performance optimization should focus on server response times, asset compression (GZIP/Brotli),"
        " and removing render-blocking resources. For search, ensure canonical tags are correctly configured,"
        " structured data is consistent, and broken internal/external links are resolved. Security can be"
        " strengthened by enforcing HTTPS site-wide and deploying headers such as CSP, HSTS, and X-Frame-Options.",
        "We recommend implementing a weekly remediation plan, followed by a daily light audit and a monthly"
        " full audit to track progress. FF Tech’s certified report provides a baseline and clear prioritization."
        " By resolving the highlighted issues, the website will deliver faster experiences, better rankings,"
        " and stronger compliance suitable for stakeholders and regulators."
    ]
    body = " ".join(words)
    return " ".join(body.split()[:200])

def compute_audit(website_url: str) -> Dict[str, Any]:
    url = normalize_url(website_url)
    status, body, headers, ttfb = fetch(url)
    soup = parse_html(body) if body else BeautifulSoup("", "html.parser")
    links = find_links(soup, url)
    dom_words = count_text_words(soup)

    https_ok = is_https(url)
    domain = extract_domain(url)
    ssl_info = resolve_ssl(domain) if https_ok else {"valid": False, "error": "Not HTTPS"}
    sec_headers = check_security_headers(headers)

    title_tag = soup.find("title")
    meta_desc = soup.find("meta", attrs={"name": "description"})
    canonical = soup.find("link", rel="canonical")
    viewport = soup.find("meta", attrs={"name": "viewport"})
    hreflangs = soup.find_all("link", rel="alternate")
    h1 = soup.find_all("h1")
    imgs = soup.find_all("img")

    link_check = check_broken_links(links["anchors"], limit=150)
    img_check = check_broken_links(links["images"], limit=100)
    js_check = check_broken_links(links["js"], limit=60)
    css_check = check_broken_links(links["css"], limit=60)
    rob_smap = check_robot_sitemap(url)

    mixed_content = []
    if https_ok:
        for group in ("anchors", "images", "css", "js"):
            mixed_content += [u for u in links[group] if u.startswith("http://")]

    content_encoding = headers.get("Content-Encoding", headers.get("content-encoding", "")).lower()
    compression_enabled = ("gzip" in content_encoding) or ("br" in content_encoding)

    total_size_bytes = sizeof_response(headers, body)
    resource_load_errors = len(img_check["broken"]) + len(js_check["broken"]) + len(css_check["broken"])

    title_missing = (title_tag is None)
    meta_desc_missing = (meta_desc is None)
    h1_missing = (len(h1) == 0)
    multiple_h1 = (len(h1) > 1)
    viewport_present = viewport is not None
    canonical_missing = canonical is None
    canonical_incorrect = False
    if canonical and canonical.get("href"):
        canonical_url = canonical["href"]
        canonical_incorrect = extract_domain(canonical_url) != domain

    hreflang_missing = (len(hreflangs) == 0)
    missing_alt = sum(1 for i in imgs if not i.get("alt"))

    text_len = len(soup.get_text()) if body else 0
    html_len = len(body) if body else 1
    text_html_ratio = (text_len / html_len) if html_len else 0.0

    errors, warnings, notices = [], [], []

    if status == 0 or status >= 500:
        errors.append("Server error or unreachable")
    elif status >= 400:
        errors.append(f"Page returned HTTP {status}")

    if title_missing: warnings.append("Missing title tag")
    if meta_desc_missing: warnings.append("Missing meta description")
    if h1_missing: warnings.append("Missing H1")
    if multiple_h1: notices.append("Multiple H1 tags found")
    if canonical_missing: warnings.append("Missing canonical tag")
    if canonical_incorrect: warnings.append("Canonical tag points to different domain")
    if not viewport_present: warnings.append("Missing viewport meta tag (mobile)")
    if hreflang_missing: notices.append("Hreflang tags missing")
    if not compression_enabled: warnings.append("Compression (GZIP/Brotli) not enabled")
    if not https_ok: errors.append("Site not served over HTTPS")
    if https_ok and not ssl_info.get("valid"):
        warnings.append("SSL certificate retrieval failed or invalid")

    if len(link_check["broken"]) > 0:
        errors.append(f"Broken links detected: {len(link_check['broken'])}")
    if len(img_check["broken"]) > 0:
        warnings.append(f"Broken images detected: {len(img_check['broken'])}")
    if len(js_check["broken"]) > 0:
        warnings.append(f"Broken JS references detected: {len(js_check['broken'])}")
    if len(css_check["broken"]) > 0:
        warnings.append(f"Broken CSS references detected: {len(css_check['broken'])}")

    if len(mixed_content) > 0:
        warnings.append(f"Mixed content (HTTP on HTTPS) resources: {len(mixed_content)}")

    if dom_words < 300:
        warnings.append("Thin content (<300 words)")
    if text_html_ratio < 0.1:
        notices.append("Low text-to-HTML ratio")

    if ttfb > 0.8:
        warnings.append(f"Slow server response (TTFB ~ {ttfb:.2f}s)")
    if total_size_bytes > 2_000_000:
        warnings.append("Total page size is high (>2MB)")
    num_requests = len(links["images"]) + len(links["js"]) + len(links["css"]) + len(links["anchors"])
    if num_requests > 200:
        notices.append("High number of resource requests (>200)")

    sec_missing = [k for k, present in sec_headers.items() if not present]
    if sec_missing:
        warnings.append(f"Missing security headers: {', '.join(sec_missing)}")

    if not rob_smap["robots_found"]:
        notices.append("robots.txt not found")
    if rob_smap["sitemap_status"] != 200:
        warnings.append("sitemap.xml not found or not accessible")

    score = 100.0
    score -= min(50.0, 10.0 * len(errors))
    score -= min(30.0, 2.0 * len(warnings))
    score -= min(10.0, 0.5 * len(notices))
    score -= min(15.0, 0.02 * len(link_check["broken"]))
    score -= min(6.0, 0.01 * num_requests)
    score -= 5.0 if not viewport_present else 0.0
    score -= 6.0 if not compression_enabled else 0.0
    score -= 8.0 if not https_ok else 0.0
    score = max(0.0, min(100.0, score))
    grade = grade_from_score(score)

    weaknesses = []
    weaknesses += errors
    weaknesses += warnings[:10]
    if len(mixed_content) > 0:
        weaknesses.append("Mixed content risks")
    if missing_alt > 0:
        weaknesses.append(f"Images missing alt: {missing_alt}")
    if canonical_incorrect:
        weaknesses.append("Incorrect canonical domain")

    metrics = {
        "site_health_score": round(score, 2),
        "grade": grade,
        "total_errors": len(errors),
        "total_warnings": len(warnings),
        "total_notices": len(notices),
        "audit_completion": "complete",

        "http_status": status,
        "redirected_links_count": len(link_check["redirected"]),
        "broken_internal_external_links": len(link_check["broken"]),
        "robots_txt_found": rob_smap["robots_found"],
        "sitemap_status_code": rob_smap["sitemap_status"],
        "sitemap_size_bytes": rob_smap["sitemap_size_bytes"],

        "title_missing": title_missing,
        "meta_desc_missing": meta_desc_missing,
        "h1_missing": h1_missing,
        "multiple_h1": multiple_h1,
        "canonical_missing": canonical_missing,
        "canonical_incorrect": canonical_incorrect,
        "viewport_present": viewport_present,
        "hreflang_missing": hreflang_missing,
        "missing_alt_count": missing_alt,
        "text_to_html_ratio": round(text_html_ratio, 3),

        "ttfb_seconds": round(ttfb, 3),
        "total_page_size_bytes": total_size_bytes,
        "num_requests_estimate": num_requests,
        "compression_enabled": compression_enabled,
        "resource_load_errors": resource_load_errors,

        "https": https_ok,
        "ssl_valid": ssl_info.get("valid", False),
        "security_headers_present": check_security_headers(headers),
        "mixed_content_count": len(mixed_content),
    }

    # Extras for your template
    competitors = [
        {"name": "Competitor A", "score": max(20, int(metrics["site_health_score"] - 10))},
        {"name": "Competitor B", "score": max(15, int(metrics["site_health_score"] - 5))},
    ]
    top_issues = []
    for msg in weaknesses[:10]:
        sev = "high" if "error" in msg.lower() else ("medium" if "warning" in msg.lower() else "low")
        top_issues.append({"name": msg, "severity": sev, "suggestion": "Investigate and remediate."})

    recommendations = {
        "compression_enabled": "Enable GZIP/Brotli on server or CDN.",
        "viewport_present": "Add <meta name='viewport' ...> for mobile responsiveness.",
        "ttfb_seconds": "Reduce TTFB via caching, DB optimization, and CDN.",
        "mixed_content_count": "Serve all resources via HTTPS to avoid mixed content.",
        "missing_alt_count": "Add alt attributes to images for accessibility."
    }

    return {
        "metrics": metrics,
        "weaknesses": weaknesses,
        "competitors": competitors,
        "top_issues": top_issues,
        "recommendations": recommendations
    }

# -----------------------------------------------------------------------------
# PDF Report (Certified)
# -----------------------------------------------------------------------------
def wrap_text(text: str, max_chars: int = 90) -> List[str]:
    words = text.split()
    lines, line, count = [], [], 0
    for w in words:
        if count + len(w) + 1 > max_chars:
            lines.append(" ".join(line)); line = [w]; count = len(w)
        else:
            line.append(w); count += len(w) + 1
    if line: lines.append(" ".join(line))
    return lines

def generate_pdf(report: Dict[str, Any], website_url: str, path: str):
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    c.setFillColorRGB(0.1, 0.2, 0.5); c.rect(0, height - 2.5*cm, width, 2.5*cm, fill=True, stroke=False)
    c.setFillColorRGB(1, 1, 1); c.setFont("Helvetica-Bold", 16)
    c.drawString(1.5*cm, height - 1.5*cm, FFTECH_LOGO_TEXT + " • Certified Audit Report")
    c.setFillColorRGB(0.1, 0.6, 0.1); c.setFont("Helvetica-Bold", 12)
    c.drawRightString(width - 1.5*cm, height - 1.5*cm, FFTECH_CERT_STAMP_TEXT)

    c.setFillColorRGB(0,0,0)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(2*cm, height - 3.5*cm, f"Website: {website_url}")
    c.drawString(2*cm, height - 4.2*cm, f"Date: {dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    m = report["metrics"]
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2*cm, height - 5.2*cm, f"Grade: {m.get('grade','N/A')}  |  Score: {m.get('site_health_score',0)}%")
    c.setFont("Helvetica", 10)
    y = height - 6.2*cm
    for k in ["http_status","ttfb_seconds","compression_enabled","robots_txt_found","sitemap_status_code","mixed_content_count","total_page_size_bytes","num_requests_estimate","title_missing","meta_desc_missing","h1_missing","canonical_missing","ssl_valid","viewport_present","missing_alt_count"]:
        c.drawString(2*cm, y, f"{k.replace('_',' ').title()}: {m.get(k)}"); y -= 0.5*cm
        if y < 2.5*cm: c.showPage(); y = height - 2.5*cm; c.setFont("Helvetica", 10)
    c.setFont("Helvetica-Bold", 12); c.drawString(2*cm, y, "Executive Summary"); y -= 0.6*cm
    c.setFont("Helvetica", 10)
    summary = generate_summary(website_url, m, report["weaknesses"])
    for line in wrap_text(summary, max_chars=95):
        c.drawString(2*cm, y, line); y -= 0.45*cm
        if y < 2.5*cm: c.showPage(); y = height - 2.5*cm; c.setFont("Helvetica", 10)
    c.showPage(); c.save()

# -----------------------------------------------------------------------------
# Startup: create schema + auto-migrate + auto-seed
# -----------------------------------------------------------------------------
def ensure_columns(conn, table: str, cols: Dict[str, str]):
    for col, sqltype in cols.items():
        check_sql = text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :tname AND column_name = :cname
        """)
        exists = conn.execute(check_sql, {"tname": table, "cname": col}).fetchone()
        if not exists:
            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {sqltype}'))

def get_latest_audit(db: Session) -> Optional[AuditRun]:
    try:
        return db.query(AuditRun).order_by(AuditRun.id.desc()).first()
    except SQLAlchemyError:
        return None

def ensure_first_audit(db: Session):
    """Auto-seed the first audit if none exist and AUTO_SEED_AUDIT_URL is set."""
    seed_url = AUTO_SEED_AUDIT_URL
    if not seed_url:
        return
    latest = get_latest_audit(db)
    if latest:
        return
    w = db.query(Website).filter(Website.url == seed_url).first()
    if not w:
        w = Website(user_id=None, url=seed_url)
        db.add(w); db.commit()
    a = compute_audit(seed_url)
    metrics, weaknesses = a["metrics"], a["weaknesses"]
    run = AuditRun(
        website_id=w.id,
        finished_at=func.now(),
        site_health_score=metrics["site_health_score"],
        grade=metrics["grade"],
        metrics_summary=metrics,
        weaknesses=weaknesses,
        executive_summary=generate_summary(seed_url, metrics, weaknesses),
        competitors=a["competitors"],
        top_issues=a["top_issues"],
        recommendations=a["recommendations"]
    )
    db.add(run); db.commit()

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        ensure_columns(conn, "users", {
            "role": "VARCHAR DEFAULT 'user'",
            "totp_enabled": "BOOLEAN DEFAULT FALSE",
            "totp_secret": "VARCHAR"
        })
        ensure_columns(conn, "audit_runs", {
            "competitors": "JSON",
            "top_issues": "JSON",
            "recommendations": "JSON"
        })
    # Auto-seed first audit if required
    try:
        db = SessionLocal()
        ensure_first_audit(db)
    finally:
        try: db.close()
        except Exception: pass

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "time": dt.datetime.utcnow().isoformat() + "Z"}

def render_dashboard(request: Request, audit: AuditRun, website: Website, previous: Optional[AuditRun]) -> HTMLResponse:
    ctx_audit = {
        "id": audit.id,
        "finished_at": audit.finished_at,
        "grade": audit.grade,
        "site_health_score": audit.site_health_score,
        "metrics_summary": audit.metrics_summary or {},
        "weaknesses": audit.weaknesses or [],
        "executive_summary": audit.executive_summary or "",
        "website": {"url": website.url},
        "competitors": audit.competitors or [],
        "top_issues": audit.top_issues or [],
        "recommendations": audit.recommendations or {},
    }
    # Prefer file-based template if available
    if templates is not None and (templates_dir / "index.html").exists():
        return templates.TemplateResponse("index.html", {"request": request, "audit": ctx_audit, "previous_audit": previous})
    # Otherwise render inline
    from jinja2 import Environment, select_autoescape
    env = Environment(autoescape=select_autoescape(enabled_extensions=("html",)))
    tpl = env.from_string(INLINE_HTML)
    html = tpl.render(audit=ctx_audit, previous_audit=previous)
    return HTMLResponse(html)

@app.get("/", response_class=HTMLResponse)
def root(request: Request, db: Session = Depends(get_db)):
    port_label = os.getenv("PORT", "8080")
    # Always try to show the latest audit at '/'
    try:
        latest = get_latest_audit(db)
        if latest:
            website = db.query(Website).get(latest.website_id)
            previous = (
                db.query(AuditRun)
                .filter(AuditRun.website_id == website.id, AuditRun.id < latest.id)
                .order_by(AuditRun.id.desc())
                .first()
            )
            return render_dashboard(request, latest, website, previous)
    except SQLAlchemyError:
        pass  # fall through to status page

    # Styled status page (Tailwind tag FIXED)
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>FF Tech | System Online</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        https://cdn.tailwindcss.com</script>
    </head>
    <body class="bg-slate-900 text-white flex items-center justify-center min-h-screen">
        <div class="p-12 border border-white/10 rounded-3xl text-center shadow-2xl max-w-xl">
            <h1 class="text-4xl md:text-6xl font-black mb-4">SYSTEM <span class="text-indigo-500">READY</span></h1>
            <p class="text-slate-400 text-lg">Audit Engine is listening for instructions...</p>
            <div class="mt-6 flex gap-3 justify-center">
                <span class="px-4 py-1 bg-emerald-500/20 text-emerald-400 rounded-full text-sm font-bold">● LIVE</span>
                <span class="px-4 py-1 bg-indigo-500/20 text-indigo-400 rounded-full text-sm font-bold">PORT: {port_label}</span>
            </div>
            <div class="mt-6">
                <p class="text-slate-400 text-sm">Run a first audit to see the dashboard:</p>
                <code class="text-xs bg-white/10 px-2 py-1 rounded">
                    curl -X POST {APP_DOMAIN}/audit/run -H "Content-Type: application/json" -d '{{"website_url":"https://example.com"}}'
                </code>
            </div>
        </div>
    </body>
    </html>
    """

@app.post("/audit/run")
def run_audit(data: AuditStartRequest, db: Session = Depends(get_db)):
    w = db.query(Website).filter(Website.url == data.website_url).first()
    if not w:
        w = Website(user_id=None, url=data.website_url)
        db.add(w); db.commit()
    a = compute_audit(w.url)
    metrics = a["metrics"]; weaknesses = a["weaknesses"]
    run = AuditRun(
        website_id=w.id,
        finished_at=func.now(),
        site_health_score=metrics["site_health_score"],
        grade=metrics["grade"],
        metrics_summary=metrics,
        weaknesses=weaknesses,
        executive_summary=generate_summary(w.url, metrics, weaknesses),
        competitors=a["competitors"],
        top_issues=a["top_issues"],
        recommendations=a["recommendations"]
    )
    db.add(run); db.commit()
    report_url = f"{APP_DOMAIN}/audit/{run.id}/report"
    return {"message": "Audit completed", "audit_id": run.id, "grade": run.grade, "score": run.site_health_score, "report_url": report_url}

@app.get("/audit/{audit_id}/report", response_class=HTMLResponse)
def audit_report(audit_id: int, request: Request, db: Session = Depends(get_db)):
    run = db.query(AuditRun).get(audit_id)
    if not run:
        raise HTTPException(status_code=404, detail="Audit not found")
    website = db.query(Website).get(run.website_id)
    previous = (
        db.query(AuditRun)
        .filter(AuditRun.website_id == website.id, AuditRun.id < audit_id)
        .order_by(AuditRun.id.desc())
        .first()
    )
    return render_dashboard(request, run, website, previous)

@app.get("/audit/{audit_id}/pdf")
def pdf_report(audit_id: int, db: Session = Depends(get_db)):
    run = db.query(AuditRun).get(audit_id)
    if not run:
        raise HTTPException(status_code=404, detail="Audit not found")
    website = db.query(Website).get(run.website_id)
    filepath = f"/tmp/fftech_report_{audit_id}.pdf"
    generate_pdf({"metrics": run.metrics_summary, "weaknesses": run.weaknesses}, website.url, filepath)
    try:
        with open(filepath, "rb") as f:
            content = f.read()
        return Response(content, media_type="application/pdf")
    finally:
        try: os.remove(filepath)
        except Exception: pass

# -----------------------------------------------------------------------------
# Optional Scheduler (running but no jobs unless you add them)
# -----------------------------------------------------------------------------
scheduler = BackgroundScheduler(daemon=True)
scheduler.start()

def schedule_audit_job(website_url: str):
    db = SessionLocal()
    try:
        run_audit(AuditStartRequest(website_url=website_url), db)
    finally:
        db.close()

# -----------------------------------------------------------------------------
# Local run helper
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
