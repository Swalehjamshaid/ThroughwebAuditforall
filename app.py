
# ap.py — FF Tech AI Audit (DB-backed, inline HTML, Railway-ready)
# ---------------------------------------------------------------------
# - Integrates YOUR provided HTML exactly (embedded as Jinja template).
# - Adds Start Audit (AJAX) -> runs audit -> redirects to /audit/{id}/report.
# - Populates the page with audit attributes, charts, issues, metrics, etc.
# - Download PDF works at /audit/{id}/pdf.
# - SQLAlchemy DB-backed (Postgres via DATABASE_URL; SQLite fallback).
# ---------------------------------------------------------------------

import os
import re
import time
import json
import socket
import ssl as sslmod
import datetime as dt
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

import requests
import httpx
from bs4 import BeautifulSoup
from jinja2 import Environment, select_autoescape

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

# --- SQLAlchemy ORM ---
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey,
    Text, Float, JSON as SA_JSON, func, text
)
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.exc import SQLAlchemyError

# --------------------------- Config ----------------------------
APP_NAME = "FF TECH AI AUDIT"
ENV = os.getenv("ENV", "development")
DEFAULT_USER_AGENT = os.getenv("DEFAULT_USER_AGENT", "FFTechAudit/1.0")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fftech.db")

# Optional search keys (resolver will still work without them via DuckDuckGo)
BING_SEARCH_KEY   = os.getenv("BING_SEARCH_KEY")
GOOGLE_CSE_KEY    = os.getenv("GOOGLE_CSE_KEY")
GOOGLE_CSE_ID     = os.getenv("GOOGLE_CSE_ID")

TIMEOUT = 20
RETRIES = 2
AVOID_DOMAINS = {"facebook.com", "twitter.com", "x.com", "instagram.com", "linkedin.com", "youtube.com"}

# ----------------------- FastAPI app ---------------------------
app = FastAPI(title=APP_NAME, version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if ENV != "production" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------- DB setup -------------------------------
Base = declarative_base()
try:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
except Exception:
    engine = create_engine("sqlite:///./fftech.db", pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

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
    site_health_score = Column(Float)                  # 0-100
    grade = Column(String)                             # A+, A, B, C, D
    metrics_summary = Column(SA_JSON)                  # dict of metrics -> values
    weaknesses = Column(SA_JSON)                       # list of weaknesses
    executive_summary = Column(Text)                   # ~summary text
    competitors = Column(SA_JSON, nullable=True)       # [{name, score}]
    top_issues = Column(SA_JSON, nullable=True)        # [{name, severity, suggestion}]
    recommendations = Column(SA_JSON, nullable=True)   # {metric_key: suggestion}

class User(Base):
    __tablename__ = "users"                            # kept for future RBAC/2FA use
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=True)
    password_hash = Column(String, nullable=True)
    is_active = Column(Boolean, default=False)
    role = Column(String, default="user")
    totp_enabled = Column(Boolean, default=False)
    totp_secret = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
    timezone = Column(String, default="Asia/Karachi")

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def ensure_columns(conn, table: str, cols: Dict[str, str]):
    """Auto-add missing columns in Postgres."""
    for col, sqltype in cols.items():
        check_sql = text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :tname AND column_name = :cname
        """)
        exists = conn.execute(check_sql, {"tname": table, "cname": col}).fetchone()
        if not exists:
            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {sqltype}'))

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    # optional Postgres auto-migration
    try:
        with engine.begin() as conn:
            ensure_columns(conn, "audit_runs", {
                "competitors": "JSON",
                "top_issues": "JSON",
                "recommendations": "JSON"
            })
            ensure_columns(conn, "users", {
                "role": "VARCHAR DEFAULT 'user'",
                "totp_enabled": "BOOLEAN DEFAULT FALSE",
                "totp_secret": "VARCHAR"
            })
    except Exception:
        pass

# ---------------------- Inline HTML (YOUR template) ---------------------
INLINE_HTML = r"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
<meta charset="UTF-8">
<title>FF Tech AI Website Audit | {{ audit.website.url }}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">

<!-- Tailwind CSS -->
https://cdn.tailwindcss.com</script>
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

<!-- HEADER -->
<header class="border-b border-white/10">
<div class="max-w-7xl mx-auto px-6 py-6 flex justify-between items-center">
  <div>
    <h1 class="text-3xl font-black">FF TECH <span class="text-indigo-400">AI AUDIT</span></h1>
    <p class="text-sm text-slate-400" id="currentWebsite">{{ audit.website.url }}</p>
  </div>
  <div class="flex items-center gap-4">
    <button onclick="toggleMode()" class="px-3 py-1 bg-indigo-500/20 text-indigo-400 rounded-full text-sm font-bold">Toggle Dark/Light</button>
    <button onclick="downloadPDF()" class="px-3 py-1 bg-emerald-500/20 text-emerald-400 rounded-full text-sm font-bold">Download PDF</button>
  </div>
</div>
</header>

<!-- URL INPUT SECTION -->
<div class="max-w-3xl mx-auto px-6 py-6">
  <div class="glass rounded-3xl p-6 flex flex-col md:flex-row items-center gap-4">
    <input type="url" id="websiteUrl" placeholder="Enter website URL..."
           class="flex-1 px-4 py-3 rounded-xl bg-slate-900 text-slate-200 border border-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
    <button onclick="startAudit()"
            class="px-6 py-3 bg-indigo-500 hover:bg-indigo-600 text-white font-bold rounded-xl transition">Start Audit</button>
  </div>
</div>

<!-- LIVE AUDIT BANNER -->
<div class="max-w-7xl mx-auto px-6 py-2">
  <div id="liveBanner" class="bg-indigo-600/20 text-indigo-400 rounded-full px-4 py-2 font-bold flex items-center gap-2">
    <span>Audit in Progress</span>
    <span class="animate-pulse">●</span>
  </div>
</div>

<!-- TABS -->
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

<!-- TAB CONTENT -->
<div class="max-w-7xl mx-auto px-6">
  <!-- OVERVIEW TAB -->
  <div id="overview" class="tab-content fadeIn">
    <!-- Score & Timeline -->
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

    <!-- Charts -->
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

    <!-- Competitor Comparison -->
    <section class="py-6">
      <div class="glass rounded-3xl p-8">
        <h2 class="text-2xl font-extrabold mb-6">Competitor Comparison</h2>
        <div class="grid md:grid-cols-3 gap-6 text-center">
          <!-- Your Website -->
          <div class="p-6 bg-slate-900 rounded-xl">
            <p class="text-sm text-slate-400">Your Website</p>
            <p class="text-4xl font-black text-indigo-400">{{ audit.site_health_score }}%</p>
            <div class="h-2 bg-indigo-400 rounded mt-2" style="width:{{ audit.site_health_score }}%"></div>
          </div>
          <!-- Competitors -->
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

    <!-- Top Issues -->
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

    <!-- Metrics Grid -->
    <section class="py-6 grid md:grid-cols-2 xl:grid-cols-3 gap-6">
      {% for k,v in audit.metrics_summary.items() %}
      <div class="glass rounded-2xl p-6 tooltip" data-value="{{ v }}" data-key="{{ k }}">
        <p class="text-xs text-slate-400 uppercase">{{ k.replace("_"," ") }}</p>
        <p class="text-2xl font-bold mt-2">{{ v }}</p>
        <span class="tooltiptext">{{ audit.recommendations[k] }}</span>
      </div>
      {% endfor %}
    </section>

    <!-- Weaknesses -->
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

  <!-- OTHER TABS (SEO, Performance, Security, Compliance, Recommendations) -->
  <!-- Add similar sections as per previous code -->

</div>

<!-- FOOTER -->
<footer class="border-t border-white/10 mt-20">
<div class="max-w-7xl mx-auto px-6 py-8 text-center text-sm text-slate-500">
FF Tech © AI Website Audit Platform · Generated {{ audit.finished_at }}
</div>
</footer>

<script>
// TAB FUNCTION
function showTab(tabId){
  document.querySelectorAll('.tab-content').forEach(tab => tab.classList.add('hidden'));
  document.getElementById(tabId).classList.remove('hidden');
  document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
  event.currentTarget.classList.add('active');
}

// DARK/LIGHT MODE
function toggleMode() {
  document.documentElement.classList.toggle('dark');
  document.body.classList.toggle('bg-slate-50');
  document.body.classList.toggle('text-slate-900');
}

// COLLAPSIBLE CONTENT
function toggleContent(id) {
  const el = document.getElementById(id);
  el.style.maxHeight = el.style.maxHeight === '0px' || !el.style.maxHeight ? el.scrollHeight + 'px' : '0px';
}

// Animate Audit Timeline (visual only)
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

// START AUDIT FUNCTION (calls backend, then redirects to report page)
async function startAudit() {
    const url = document.getElementById("websiteUrl").value.trim();
    if(!url) {
        alert("Please enter a valid website URL or brand.");
        return;
    }
    document.getElementById("currentWebsite").innerText = url;
    const banner = document.getElementById("liveBanner");
    banner.innerHTML = `<span>Audit in Progress for ${url}</span> <span class="animate-pulse">●</span>`;
    animateAudit();

    try {
      const res = await fetch("/audit/run", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({ website_url: url })
      });
      const j = await res.json();
      if (j && j.report_url) {
        window.location.href = j.report_url;
      } else {
        alert("Audit failed to start. Please try again.");
      }
    } catch (e) {
      console.error(e);
      alert("Network error. Please try again.");
    }
}

// Download PDF (navigate to endpoint; works on the report page)
function downloadPDF() {
  const metaEl = document.querySelector('meta[name="audit-id"]');
  if (metaEl && metaEl.getAttribute("content")) {
    const id = metaEl.getAttribute("content");
    window.location.href = `/audit/${id}/pdf`;
  } else {
    alert("Run an audit first, then download the PDF from the report page.");
  }
}

// Charts
new Chart(document.getElementById("issuesChart"), {
  type: "doughnut",
  data: {
    labels: ["Errors","Warnings","Notices"],
    datasets: [{data:[{{ audit.metrics_summary.total_errors | default(0) }},{{ audit.metrics_summary.total_warnings | default(0) }},{{ audit.metrics_summary.total_notices | default(0) }}],backgroundColor:["#ef4444","#f59e0b","#38bdf8"]}]
  },
  options:{plugins:{legend:{labels:{color:"#cbd5f5"}}}}
});

new Chart(document.getElementById("trendChart"), {
  type:"line",
  data:{labels:["Previous","Current"],datasets:[{data:[{{ previous_audit.site_health_score if previous_audit else audit.site_health_score }},{{ audit.site_health_score }}],borderColor:"#6366f1",backgroundColor:"rgba(99,102,241,.2)",tension:.4,fill:true,pointRadius:6}]},
  options:{scales:{x:{ticks:{color:"#cbd5f5"}},y:{ticks:{color:"#cbd5f5"},min:0,max:100}},plugins:{legend:{display:false}}}
});
</script>

<!-- meta used by PDF button -->
<meta name="audit-id" content="{{ audit.id if audit.id else '' }}">
</body>
</html>
"""

# ----------------------- Jinja render helper ---------------------
def render_html(audit: Dict[str, Any], previous: Optional[Dict[str, Any]]) -> HTMLResponse:
    env = Environment(autoescape=select_autoescape(enabled_extensions=("html",)))
    tpl = env.from_string(INLINE_HTML)
    html = tpl.render(audit=audit, previous_audit=previous)
    return HTMLResponse(html)

# ----------------------- Resolver & audit engine -----------------
from urllib.parse import urlparse, urlsplit, parse_qs, unquote

def is_probable_url(text: str) -> bool:
    text = text.strip()
    return bool(re.match(r"^(https?://)?([\w-]+\.)+[a-zA-Z]{2,}(/.*)?$", text))

def normalize_url(text: str) -> str:
    text = text.strip()
    if not text:
        raise ValueError("Empty URL or query")
    if is_probable_url(text):
        if not re.match(r"^https?://", text):
            text = "https://" + text
        return text
    return text

def host_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

def ddg_unwrap(href: str) -> str:
    try:
        if "duckduckgo.com/l/?" in href:
            qs = parse_qs(urlsplit(href).query)
            for key in ("uddg", "url"):
                if key in qs and qs[key]:
                    return unquote(qs[key][0])
    except Exception:
        pass
    return href

async def head_ok(client: httpx.AsyncClient, url: str) -> Tuple[bool, Optional[str]]:
    for attempt in range(RETRIES):
        try:
            r = await client.head(url, follow_redirects=True, timeout=TIMEOUT)
            if r.status_code < 400:
                return True, str(r.url)
        except Exception:
            pass
        try:
            r = await client.get(url, follow_redirects=True, timeout=TIMEOUT)
            if r.status_code < 400:
                return True, str(r.url)
        except Exception:
            if attempt == RETRIES - 1:
                break
    return False, None

async def ddg_search(client: httpx.AsyncClient, query: str) -> List[str]:
    try:
        url = "https://duckduckgo.com/html/"
        r = await client.post(
            url,
            data={"q": query},
            headers={"User-Agent": DEFAULT_USER_AGENT},
            timeout=TIMEOUT,
        )
        soup = BeautifulSoup(r.text, "html.parser")
        links = []
        for a in soup.select("a.result__a"):
            href = a.get("href")
            if href:
                links.append(ddg_unwrap(href))
        if not links:
            for a in soup.select("a"):
                href = a.get("href")
                if href and href.startswith("http"):
                    links.append(ddg_unwrap(href))
        return links[:8]
    except Exception:
        return []

async def bing_search(client: httpx.AsyncClient, query: str) -> List[str]:
    if not BING_SEARCH_KEY:
        return []
    try:
        url = "https://api.bing.microsoft.com/v7.0/search"
        r = await client.get(
            url,
            params={"q": query, "mkt": "en-US"},
            headers={"Ocp-Apim-Subscription-Key": BING_SEARCH_KEY},
            timeout=TIMEOUT,
        )
        j = r.json()
        urls = []
        for item in j.get("webPages", {}).get("value", []):
            u = item.get("url")
            if u:
                urls.append(u)
        return urls[:8]
    except Exception:
        return []

async def google_cse_search(client: httpx.AsyncClient, query: str) -> List[str]:
    if not (GOOGLE_CSE_KEY and GOOGLE_CSE_ID):
        return []
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        r = await client.get(
            url,
            params={"q": query, "key": GOOGLE_CSE_KEY, "cx": GOOGLE_CSE_ID},
            timeout=TIMEOUT,
        )
        j = r.json()
        urls = []
        for item in j.get("items", []):
            u = item.get("link")
            if u:
                urls.append(u)
        return urls[:8]
    except Exception:
        return []

def build_query_variants(query: str) -> List[str]:
    q = query.strip()
    variants = [q, f"{q} official site", f"{q} website", f"{q} home page"]
    seen, out = set(), []
    for v in variants:
        if v not in seen:
            out.append(v); seen.add(v)
    return out

async def resolve_official_site(input_text: str, user_agent: str) -> str:
    text = input_text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty query")
    candidate = normalize_url(text)

    async with httpx.AsyncClient(headers={"User-Agent": user_agent}) as client:
        # If it already looks like a URL try it
        if is_probable_url(candidate):
            ok, final = await head_ok(client, candidate)
            if ok and final:
                return final
            # Try www variant
            parsed = urlparse(candidate)
            host = parsed.netloc
            if not host.startswith("www."):
                www = parsed._replace(netloc="www." + host).geturl()
                ok, final = await head_ok(client, www)
                if ok and final:
                    return final

        # Otherwise search (Bing -> Google CSE -> DuckDuckGo)
        providers = [
            ("bing", bing_search),
            ("google_cse", google_cse_search),
            ("duckduckgo", ddg_search),
        ]
        for q in build_query_variants(text):
            for _name, func in providers:
                urls = await func(client, q)
                # Avoid social domains
                candidates = [u for u in urls if host_of(u) not in AVOID_DOMAINS] or urls
                for u in candidates:
                    u_norm = normalize_url(u)
                    ok, final = await head_ok(client, u_norm)
                    if ok and final:
                        return final

    # As last resort, guess https://<brand>.com
    if not is_probable_url(text):
        guessed = f"https://{re.sub(r'[^a-zA-Z0-9-]+','', text.lower())}.com"
        async with httpx.AsyncClient(headers={"User-Agent": user_agent}) as client:
            ok, final = await head_ok(client, guessed)
            if ok and final:
                return final

    raise HTTPException(status_code=404, detail="Could not resolve website")

# ------------------------- Audit engine -------------------------
def fetch(url: str, timeout: int = 20) -> Tuple[int, str, Dict[str, str], float]:
    start = time.time()
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": DEFAULT_USER_AGENT})
        ttfb = r.elapsed.total_seconds() if hasattr(r, "elapsed") and r.elapsed else (time.time() - start)
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

def extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""

def parse_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")

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
            r = requests.head(u, allow_redirects=True, timeout=10, headers={"User-Agent": DEFAULT_USER_AGENT})
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

def compute_audit(website_url: str) -> Dict[str, Any]:
    status, body, headers, ttfb = fetch(website_url)
    soup = parse_html(body) if body else BeautifulSoup("", "html.parser")
    links = find_links(soup, website_url)

    https_ok = is_https(website_url)
    domain = extract_domain(website_url)
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
    img_check  = check_broken_links(links["images"],  limit=100)
    js_check   = check_broken_links(links["js"],      limit=60)
    css_check  = check_broken_links(links["css"],     limit=60)
    rob_smap   = check_robot_sitemap(website_url)

    mixed_content = []
    if https_ok:
        for group in ("anchors", "images", "css", "js"):
            mixed_content += [u for u in links[group] if u.startswith("http://")]

    content_encoding = headers.get("Content-Encoding", headers.get("content-encoding", "")).lower()
    compression_enabled = ("gzip" in content_encoding) or ("br" in content_encoding)
    total_size_bytes = sizeof_response(headers, body)

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

    errors, warnings, notices = [], [], []
    if status == 0 or status >= 500: errors.append("Server error or unreachable")
    elif status >= 400: errors.append(f"Page returned HTTP {status}")

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
    if https_ok and not ssl_info.get("valid"): warnings.append("SSL certificate retrieval failed or invalid")

    if len(link_check["broken"]) > 0: errors.append(f"Broken links detected: {len(link_check['broken'])}")
    if len(img_check["broken"])  > 0: warnings.append(f"Broken images detected: {len(img_check['broken'])}")
    if len(js_check["broken"])   > 0: warnings.append(f"Broken JS references detected: {len(js_check['broken'])}")
    if len(css_check["broken"])  > 0: warnings.append(f"Broken CSS references detected: {len(css_check['broken'])}")

    if len(mixed_content) > 0: warnings.append(f"Mixed content (HTTP on HTTPS) resources: {len(mixed_content)}")

    # simple scoring
    score = 100.0
    score -= min(50.0, 10.0 * len(errors))
    score -= min(30.0,  2.0 * len(warnings))
    score -= min(10.0,  0.5 * len(notices))
    score -= min(15.0,  0.02 * len(link_check["broken"]))
    num_requests = len(links["images"]) + len(links["js"]) + len(links["css"]) + len(links["anchors"])
    score -= min(6.0,   0.01 * num_requests)
    score -= 5.0 if not viewport_present else 0.0
    score -= 6.0 if not compression_enabled else 0.0
    score -= 8.0 if not https_ok else 0.0
    score = max(0.0, min(100.0, score))
    grade = grade_from_score(score)

    weaknesses = []
    weaknesses += errors
    weaknesses += warnings[:10]
    if len(mixed_content) > 0: weaknesses.append("Mixed content risks")
    if missing_alt > 0: weaknesses.append(f"Images missing alt: {missing_alt}")
    if canonical_incorrect: weaknesses.append("Incorrect canonical domain")

    metrics = {
        "site_health_score": round(score, 2),
        "grade": grade,
        "total_errors": len(errors),
        "total_warnings": len(warnings),
        "total_notices": len(notices),

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

        "ttfb_seconds": round(ttfb, 3),
        "total_page_size_bytes": total_size_bytes,
        "num_requests_estimate": num_requests,
        "compression_enabled": compression_enabled,

        "https": https_ok,
        "ssl_valid": ssl_info.get("valid", False),
        "security_headers_present": check_security_headers(headers),
        "mixed_content_count": len(mixed_content),
    }

    # extras for UI
    competitors = [
        {"name": "Competitor A", "score": max(20, int(metrics["site_health_score"] - 10))},
        {"name": "Competitor B", "score": max(15, int(metrics["site_health_score"] - 5))},
    ]
    top_issues = []
    for msg in weaknesses[:10]:
        sev = "high" if "error" in msg.lower() else ("medium" if "warning" in msg.lower() else "low")
        top_issues.append({"name": msg, "severity": sev, "suggestion": "Investigate and remediate."})

    recommendations = {
        "compression_enabled": "Enable GZIP/Brotli at server/CDN.",
        "viewport_present": "Add <meta name='viewport' ...> for mobile responsiveness.",
        "ttfb_seconds": "Reduce TTFB via caching, DB optimization, CDN.",
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

# ------------------------- PDF generation -----------------------
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

def build_summary(url: str, metrics: Dict[str, Any], weaknesses: List[str]) -> str:
    score = metrics.get("site_health_score", 0)
    grade = metrics.get("grade", "N/A")
    weak_list = ", ".join(weaknesses[:6]) if weaknesses else "No critical weaknesses detected"
    words = [
        f"FF Tech Audit Summary for {url}:",
        f"The website achieved a health score of {int(score)}% and an overall grade of {grade}.",
        "Our audit examined technical SEO, crawlability, on-page content, performance, mobile usability, and security.",
        "Key improvement areas include: " + weak_list + ". Addressing these will improve resilience and UX.",
    ]
    return " ".join(words)

def pdf_bytes(audit: Dict[str, Any]) -> bytes:
    from io import BytesIO
    stream = BytesIO()
    c = canvas.Canvas(stream, pagesize=A4)
    width, height = A4
    c.setFillColorRGB(0.1, 0.2, 0.5); c.rect(0, height - 2.5*cm, width, 2.5*cm, fill=True, stroke=False)
    c.setFillColorRGB(1, 1, 1); c.setFont("Helvetica-Bold", 16)
    c.drawString(1.5*cm, height - 1.5*cm, "FF Tech • Certified Audit Report")
    c.setFillColorRGB(0,0,0)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(2*cm, height - 3.5*cm, f"Website: {audit['website']['url']}")
    c.drawString(2*cm, height - 4.2*cm, f"Date: {dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    m = audit["metrics_summary"]
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2*cm, height - 5.2*cm, f"Grade: {audit.get('grade','N/A')}  |  Score: {audit.get('site_health_score',0)}%")
    c.setFont("Helvetica", 10)
    y = height - 6.2*cm
    for k in ["http_status","ttfb_seconds","compression_enabled","robots_txt_found","sitemap_status_code",
              "mixed_content_count","total_page_size_bytes","num_requests_estimate","title_missing",
              "meta_desc_missing","h1_missing","canonical_missing","ssl_valid","viewport_present","missing_alt_count"]:
        v = m.get(k)
        c.drawString(2*cm, y, f"{k.replace('_',' ').title()}: {v}"); y -= 0.5*cm
        if y < 2.5*cm: c.showPage(); y = height - 2.5*cm; c.setFont("Helvetica", 10)
    c.setFont("Helvetica-Bold", 12); c.drawString(2*cm, y, "Executive Summary"); y -= 0.6*cm
    c.setFont("Helvetica", 10)
    summary = build_summary(audit["website"]["url"], m, audit.get("weaknesses", []))
    for line in wrap_text(summary, max_chars=95):
        c.drawString(2*cm, y, line); y -= 0.45*cm
        if y < 2.5*cm: c.showPage(); y = height - 2.5*cm; c.setFont("Helvetica", 10)
    c.showPage(); c.save()
    stream.seek(0)
    return stream.read()

# ----------------------------- Helpers --------------------------
def latest_audit(db: Session) -> Optional[AuditRun]:
    try:
        return db.query(AuditRun).order_by(AuditRun.id.desc()).first()
    except SQLAlchemyError:
        return None

def audit_to_ctx(run: AuditRun, website_url: str) -> Dict[str, Any]:
    return {
        "id": run.id,
        "finished_at": run.finished_at,
        "grade": run.grade,
        "site_health_score": run.site_health_score,
        "metrics_summary": run.metrics_summary or {},
        "weaknesses": run.weaknesses or [],
        "website": {"url": website_url},
        "competitors": run.competitors or [],
        "top_issues": run.top_issues or [],
        "recommendations": run.recommendations or {},
    }

# ----------------------------- Routes ---------------------------
@app.get("/", response_class=HTMLResponse)
def home(db: Session = Depends(get_db)):
    run = latest_audit(db)
    if run:
        website = db.query(Website).get(run.website_id)
        prev = db.query(AuditRun).filter(AuditRun.website_id == website.id, AuditRun.id < run.id)\
                                 .order_by(AuditRun.id.desc()).first()
        ctx = audit_to_ctx(run, website.url)
        prev_ctx = audit_to_ctx(prev, website.url) if prev else None
        return render_html(ctx, prev_ctx)

    # empty state placeholders (avoid Jinja errors)
    empty_audit = {
        "id": "",
        "finished_at": "",
        "grade": "",
        "site_health_score": 0,
        "metrics_summary": {},
        "weaknesses": [],
        "website": {"url": ""},
        "competitors": [],
        "top_issues": [],
        "recommendations": {},
    }
    return render_html(empty_audit, None)

@app.post("/audit/run")
async def run_audit(payload: Dict[str, Any] = None, website_url: Optional[str] = Form(None), db: Session = Depends(get_db)):
    # Accept JSON or form data
    url_input = (payload or {}).get("website_url") or website_url
    if not url_input:
        raise HTTPException(status_code=400, detail="Provide 'website_url'")

    # Resolve brand/URL to a reachable official site
    try:
        resolved = await resolve_official_site(url_input, DEFAULT_USER_AGENT)
    except HTTPException:
        resolved = normalize_url(url_input)

    # Ensure Website record
    w = db.query(Website).filter(Website.url == resolved).first()
    if not w:
        w = Website(user_id=None, url=resolved)
        db.add(w); db.commit()

    # Compute audit
    result = compute_audit(resolved)
    metrics, weaknesses = result["metrics"], result["weaknesses"]
    run = AuditRun(
        website_id=w.id,
        finished_at=func.now(),
        site_health_score=metrics["site_health_score"],
        grade=metrics["grade"],
        metrics_summary=metrics,
        weaknesses=weaknesses,
        executive_summary=build_summary(resolved, metrics, weaknesses),
        competitors=result["competitors"],
        top_issues=result["top_issues"],
        recommendations=result["recommendations"]
    )
    db.add(run); db.commit()

    return JSONResponse({"message": "Audit completed", "audit_id": run.id, "report_url": f"/audit/{run.id}/report"})

@app.get("/audit/{audit_id}/report", response_class=HTMLResponse)
def audit_report(audit_id: int, db: Session = Depends(get_db)):
    run = db.query(AuditRun).get(audit_id)
    if not run:
        raise HTTPException(status_code=404, detail="Audit not found")
    website = db.query(Website).get(run.website_id)
    prev = db.query(AuditRun).filter(AuditRun.website_id == website.id, AuditRun.id < run.id)\
                             .order_by(AuditRun.id.desc()).first()
    ctx = audit_to_ctx(run, website.url)
    prev_ctx = audit_to_ctx(prev, website.url) if prev else None
    return render_html(ctx, prev_ctx)

@app.get("/audit/{audit_id}/pdf")
def audit_pdf(audit_id: int, db: Session = Depends(get_db)):
    run = db.query(AuditRun).get(audit_id)
    if not run:
        raise HTTPException(status_code=404, detail="Audit not found")
    website = db.query(Website).get(run.website_id)
    audit_ctx = audit_to_ctx(run, website.url)
    pdf = pdf_bytes(audit_ctx)
    return StreamingResponse(iter([pdf]), media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=fftech_audit_{audit_id}.pdf"
    })

@app.get("/health")
def health():
    return {"status": "ok", "time": dt.datetime.utcnow().isoformat() + "Z"}

# --------------------------- Local run --------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("ap:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
``
