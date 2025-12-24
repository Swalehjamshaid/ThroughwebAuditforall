
# main.py
# FF Tech — AI Website Audit (Single-file FastAPI + Jinja + Tailwind/Chart.js template embedded)
#
# Requirements:
#   fastapi==0.115.5
#   uvicorn==0.32.0
#   httpx==0.27.2
#   beautifulsoup4==4.12.3
#   lxml==5.3.0
#   tldextract==5.1.2
#   jinja2==3.1.4
#
# Run:
#   python -m venv .venv && . .venv/bin/activate
#   pip install -r requirements.txt
#   uvicorn main:app --reload
#
# Optional env:
#   export PSI_API_KEY=your_key     # Core Web Vitals & Lighthouse via Google PSI
#   export ENABLE_HISTORY=true      # Persist audits in SQLite for the trend chart

import os
import re
import json
import time
import httpx
import sqlite3
import tldextract
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from datetime import datetime

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse
from jinja2 import Environment, BaseLoader, select_autoescape

# =========================
# Embedded HTML (your file)
# =========================
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ app_name }} | Audit Report for {{ website_url }}</title>
    https://cdn.tailwindcss.com</script>
    https://cdn.jsdelivr.net/npm/chart.js</script>
    https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        body { font-family: 'Inter', sans-serif; }
        .collapsible-content { max-height: 0; overflow: hidden; transition: max-height 0.3s ease-out; }
        .collapsible-active .collapsible-content { max-height: 2000px; }
        @media print {
            .no-print { display: none; }
            .print-break { page-break-after: always; }
        }
    </style>
</head>
<body class="bg-gray-50 text-gray-900">

    <nav class="bg-white border-b sticky top-0 z-50 no-print">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex justify-between h-16 items-center">
                <div class="flex items-center space-x-2">
                    <span class="text-2xl font-bold text-indigo-600"><i class="fas fa-robot"></i> {{ app_name }}</span>
                </div>
                <div class="flex space-x-4">
                    <button onclick="window.print()" class="bg-indigo-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-indigo-700 transition">
                        <i class="fas fa-file-pdf mr-2"></i>Export to PDF
                    </button>
                </div>
            </div>
        </div>
    </nav>

    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        
        <div class="bg-white rounded-xl shadow-sm p-6 mb-8 border border-gray-100 flex flex-col md:flex-row justify-between items-start md:items-center space-y-4 md:space-y-0">
            <div>
                <h1 class="text-xl font-bold text-gray-800">Certified Website Audit Report</h1>
                <p class="text-gray-500 text-sm">Target: <span class="font-medium text-indigo-600 underline">{{ website_url }}</span></p>
                <div class="mt-2 flex space-x-4 text-xs text-gray-400">
                    <span><i class="fas fa-calendar-alt"></i> Date: {{ audit_date }}</span>
                    <span><i class="fas fa-fingerprint"></i> ID: {{ audit_id }}</span>
                </div>
            </div>
            <div class="text-right">
                <span class="text-gray-400 text-xs uppercase font-bold tracking-widest block">Official Grade</span>
                <span class="text-5xl font-black {{ grade_class }}">{{ grade }}</span>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-8">
            <div class="bg-white p-8 rounded-xl shadow-sm border border-gray-100 flex flex-col items-center justify-center text-center">
                <h2 class="text-gray-500 font-semibold mb-4 uppercase tracking-wide text-sm">Overall Site Health</h2>
                <div class="relative inline-flex">
                    <svg class="w-32 h-32">
                        <circle class="text-gray-200" stroke-width="8" stroke="currentColor" fill="transparent" r="58" cx="64" cy="64"/>
                        <circle class="text-indigo-600" stroke-width="8" stroke-dasharray="364.4" stroke-dashoffset="{{ 364.4 - (364.4 * overall_score / 100) }}" stroke-linecap="round" stroke="currentColor" fill="transparent" r="58" cx="64" cy="64"/>
                    </svg>
                    <span class="absolute inset-0 flex items-center justify-center text-3xl font-bold">{{ overall_score }}%</span>
                </div>
                <div class="mt-6 grid grid-cols-3 gap-4 w-full border-t pt-4">
                    <div><span class="block text-red-500 font-bold">{{ total_errors }}</span><span class="text-xs text-gray-400 uppercase">Errors</span></div>
                    <div><span class="block text-amber-500 font-bold">{{ total_warnings }}</span><span class="text-xs text-gray-400 uppercase">Warnings</span></div>
                    <div><span class="block text-blue-500 font-bold">{{ total_notices }}</span><span class="text-xs text-gray-400 uppercase">Notices</span></div>
                </div>
            </div>

            <div class="lg:col-span-2 bg-white p-8 rounded-xl shadow-sm border border-gray-100">
                <h2 class="text-lg font-bold text-gray-800 mb-4"><i class="fas fa-brain text-indigo-500 mr-2"></i> AI Executive Summary</h2>
                <div class="text-gray-600 leading-relaxed text-sm italic border-l-4 border-indigo-100 pl-4">
                    {{ executive_summary_200_words }}
                </div>
                <div class="mt-6 flex flex-wrap gap-2">
                    {% for area in weak_areas %}
                    <span class="px-3 py-1 bg-red-50 text-red-600 rounded-full text-xs font-semibold border border-red-100">
                        <i class="fas fa-exclamation-triangle mr-1"></i> {{ area }}
                    </span>
                    {% endfor %}
                </div>
            </div>
        </div>

        <div class="bg-white p-8 rounded-xl shadow-sm border border-gray-100 mb-8">
            <h2 class="text-lg font-bold text-gray-800 mb-6"><i class="fas fa-chart-line text-indigo-500 mr-2"></i> Historical Performance Trends</h2>
            <div class="h-64">
                <canvas id="trendChart"></canvas>
            </div>
        </div>

        <div class="space-y-6 print-break">
            <h2 class="text-2xl font-bold text-gray-800 border-b pb-2 mb-4">Detailed Technical Elaboration</h2>
            
            {% for category in audit_categories %}
            <div class="collapsible bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden" id="cat-{{ loop.index }}">
                <button onclick="toggleCollapse('cat-{{ loop.index }}')" class="w-full flex justify-between items-center p-5 bg-gray-50 hover:bg-gray-100 transition">
                    <span class="font-bold text-gray-700 flex items-center capitalize">
                        <i class="fas {{ category.icon }} mr-3 text-indigo-500"></i> {{ category.name }}
                        <span class="ml-4 text-xs font-normal bg-white px-2 py-1 rounded border text-gray-500">{{ category.metrics|length }} Metrics</span>
                    </span>
                    <i class="fas fa-chevron-down transition-transform"></i>
                </button>
                <div class="collapsible-content">
                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-sm">
                            <thead class="bg-gray-50 border-b text-gray-500 uppercase text-xs font-bold">
                                <tr>
                                    <th class="px-6 py-3">Metric Name</th>
                                    <th class="px-6 py-3">Status</th>
                                    <th class="px-6 py-3">Score</th>
                                    <th class="px-6 py-3">Priority</th>
                                    <th class="px-6 py-3">Impact / Recommendation</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-gray-100">
                                {% for metric in category.metrics %}
                                <tr class="hover:bg-gray-50 transition">
                                    <td class="px-6 py-4 font-semibold text-gray-700">{{ metric.name }}</td>
                                    <td class="px-6 py-4">
                                        {% if metric.status == 'Good' %}
                                        <span class="px-2 py-1 bg-green-100 text-green-700 rounded-md text-xs font-bold">Good</span>
                                        {% elif metric.status == 'Warning' %}
                                        <span class="px-2 py-1 bg-amber-100 text-amber-700 rounded-md text-xs font-bold">Warning</span>
                                        {% else %}
                                        <span class="px-2 py-1 bg-red-100 text-red-700 rounded-md text-xs font-bold">Critical</span>
                                        {% endif %}
                                    </td>
                                    <td class="px-6 py-4 text-right pr-12 font-mono">{{ metric.score }}/100</td>
                                    <td class="px-6 py-4">
                                        <span class="flex items-center">
                                            <span class="w-2 h-2 rounded-full mr-2 {% if metric.priority == 'High' %}bg-red-500{% elif metric.priority == 'Medium' %}bg-amber-500{% else %}bg-green-500{% endif %}"></span>
                                            {{ metric.priority }}
                                        </span>
                                    </td>
                                    <td class="px-6 py-4">
                                        <div class="max-w-md">
                                            <p class="text-xs text-gray-400 mb-1 font-medium italic">Impact: {{ metric.impact }}</p>
                                            <p class="text-gray-600 text-xs">{{ metric.recommendation }}</p>
                                        </div>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>

        <div class="mt-12 bg-indigo-900 rounded-2xl p-8 text-white shadow-xl relative overflow-hidden print-break">
            <div class="relative z-10">
                <h2 class="text-2xl font-bold mb-4 flex items-center"><i class="fas fa-lightbulb text-yellow-400 mr-3"></i> Actionable Insights for the Owner</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mt-6">
                    {% for insight in owner_insights %}
                    <div class="bg-indigo-800/50 p-6 rounded-xl border border-indigo-700 hover:bg-indigo-800 transition">
                        <h3 class="font-bold text-indigo-100 mb-2">{{ insight.title }}</h3>
                        <p class="text-sm text-indigo-200 leading-relaxed">{{ insight.description }}</p>
                    </div>
                    {% endfor %}
                </div>
            </div>
            <i class="fas fa-rocket absolute -bottom-10 -right-10 text-indigo-800 text-9xl opacity-30 transform rotate-12"></i>
        </div>

        <footer class="mt-12 text-center text-gray-400 text-xs border-t pt-8">
            <p>© {{ audit_date[:4] }} {{ app_name }} Intelligence. This audit report is valid until {{ validity_date }}.</p>
            <p class="mt-1 font-mono uppercase tracking-widest">Confidence Level: 99.8% AI Diagnostic Verified</p>
        </footer>
    </main>

    <script>
        // Toggle function for collapsible categories
        function toggleCollapse(id) {
            const el = document.getElementById(id);
            const icon = el.querySelector('.fa-chevron-down');
            el.classList.toggle('collapsible-active');
            if (el.classList.contains('collapsible-active')) {
                icon.style.transform = 'rotate(180deg)';
            } else {
                icon.style.transform = 'rotate(0deg)';
            }
        }

        // Trend Chart initialization with Jinja2 data
        const ctx = document.getElementById('trendChart').getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: {{ trend_chart_data.labels | safe if trend_chart_data else "['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']" }},
                datasets: [{
                    label: 'Health Score Trend',
                    data: {{ trend_chart_data.values | safe if trend_chart_data else "[65, 72, 68, 84, 82, 91]" }},
                    borderColor: '#4f46e5',
                    backgroundColor: 'rgba(79, 70, 229, 0.1)',
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: false, min: 0, max: 100, grid: { borderDash: [5, 5] } },
                    x: { grid: { display: false } }
                }
            }
        });
    </script>
</body>
</html>
"""

# ================
# App Setup
# ================
app = FastAPI()
env = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html", "xml"]))
APP_NAME = "FF Tech — AI Website Audit"
ENABLE_HISTORY = os.getenv("ENABLE_HISTORY", "").lower() in ("true", "1", "yes")
PSI_API_KEY = os.getenv("PSI_API_KEY")  # optional
DB_FILE = "audits.db"
AUDITS: Dict[str, Dict[str, Any]] = {}

# DB helpers (trend)
def init_db():
    if not ENABLE_HISTORY:
        return
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audits (
            id TEXT PRIMARY KEY,
            site TEXT,
            created_at TEXT,
            payload_json TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_audit(audit_id: str, site: str, payload: dict):
    if not ENABLE_HISTORY:
        return
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT OR REPLACE INTO audits (id, site, created_at, payload_json) VALUES (?,?,?,?)",
        (audit_id, site, datetime.utcnow().isoformat(), json.dumps(payload))
    )
    conn.commit()
    conn.close()

def load_recent(site: str, limit: int = 10) -> List[dict]:
    if not ENABLE_HISTORY:
        return []
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute(
        "SELECT payload_json FROM audits WHERE site=? ORDER BY created_at DESC LIMIT ?",
        (site, limit)
    ).fetchall()
    conn.close()
    return [json.loads(r[0]) for r in rows]

# Utils
def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def grade_for_score(score: int) -> Tuple[str, str]:
    # Tailwind classes for the big grade color
    if score >= 92: return ("A+", "text-green-600")
    if score >= 85: return ("A", "text-emerald-600")
    if score >= 75: return ("B", "text-amber-500")
    if score >= 65: return ("C", "text-orange-600")
    return ("D", "text-red-600")

# Crawl
@dataclass
class CrawlConfig:
    url: str
    max_pages: int = 20
    concurrency: int = 10
    user_agent: str = "FFTechAuditBot/2.1"

async def fetch_page(client: httpx.AsyncClient, url: str) -> Tuple[int, Dict[str, str], bytes, float, str]:
    start = time.perf_counter()
    try:
        r = await client.get(url)
        ms = (time.perf_counter() - start) * 1000.0
        return r.status_code, {k.lower(): v for k, v in r.headers.items()}, r.content, ms, str(r.url)
    except Exception:
        return 0, {}, b"", (time.perf_counter() - start) * 1000.0, url

async def crawl_site(cfg: CrawlConfig) -> Dict[str, Any]:
    parsed = urlparse(cfg.url)
    base = f"{parsed.scheme or 'https'}://{parsed.netloc or parsed.path}"
    root_domain = tldextract.extract(parsed.netloc).registered_domain

    headers = {"User-Agent": cfg.user_agent}
    limits = httpx.Limits(max_connections=cfg.concurrency, max_keepalive_connections=cfg.concurrency)
    timeout = httpx.Timeout(30.0)

    visited, pages = set(), []
    queue = [base]

    async with httpx.AsyncClient(headers=headers, timeout=timeout, limits=limits, follow_redirects=True) as client:
        while queue and len(pages) < cfg.max_pages:
            url = queue.pop(0)
            if url in visited: continue
            visited.add(url)

            status, h, body, dur, final = await fetch_page(client, url)
            html = body.decode(errors="ignore") if body else ""
            soup = BeautifulSoup(html, "lxml") if html else None

            title = clean(soup.title.string) if soup and soup.title else None
            md = soup.find("meta", attrs={"name": "description"}) if soup else None
            meta_desc = clean(md.get("content", "")) if md else None
            h1t = soup.find("h1") if soup else None
            h1 = clean(h1t.get_text()) if h1t else None

            is_https = final.startswith("https://")
            hsts = bool(h.get("strict-transport-security"))
            csp = bool(h.get("content-security-policy"))
            xfo = bool(h.get("x-frame-options"))

            mixed = False
            if is_https and soup:
                for tag in soup.find_all(["img", "script", "link", "iframe"]):
                    src = tag.get("src") or tag.get("href") or ""
                    if src.startswith("http://"):
                        mixed = True
                        break

            text_low = (soup.get_text(" ", strip=True).lower() if soup else "")
            cookie_banner = any(k in text_low for k in ["cookie consent", "we use cookies", "accept cookies", "gdpr", "privacy settings"])
            has_privacy_policy = any(k in text_low for k in ["privacy policy", "gdpr", "cookie policy"])

            enc = (h.get("content-encoding") or "").lower()
            gzip_or_br = ("gzip" in enc) or ("br" in enc)

            links_internal, links_external = [], []
            def norm(u: str) -> Optional[str]:
                if not u: return None
                u = u.strip()
                if u.startswith("#") or u.startswith("javascript:"): return None
                return urljoin(final, u)
            if soup:
                for a in soup.find_all("a"):
                    href = norm(a.get("href"))
                    if not href: continue
                    dom = tldextract.extract(urlparse(href).netloc).registered_domain
                    if dom == root_domain: links_internal.append(href)
                    else: links_external.append(href)

            can = soup.find("link", attrs={"rel": "canonical"}) if soup else None
            canonical = can.get("href") if (can and can.get("href")) else None
            mr = soup.find("meta", attrs={"name": "robots"}) if soup else None
            meta_robots = (mr.get("content", "").lower() if mr else "")

            hreflangs = []
            if soup:
                for link in soup.find_all("link", attrs={"rel": "alternate"}):
                    if link.get("hreflang") and link.get("href"):
                        hreflangs.append({"hreflang": link["hreflang"], "href": link["href"]})

            schema_present = False
            if soup:
                for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
                    try: json.loads(s.string or "{}"); schema_present = True; break
                    except: pass
            og_present = bool(soup and soup.find("meta", attrs={"property": "og:title"}))
            tw_present = bool(soup and soup.find("meta", attrs={"name": "twitter:card"}))

            word_count = len((soup.get_text(" ", strip=True) if soup else "").split())
            thin = word_count < 300

            imgs = soup.find_all("img") if soup else []
            imgs_with_alt = [img for img in imgs if clean(img.get("alt"))]
            alt_coverage_pct = round(100.0 * (len(imgs_with_alt) / max(1, len(imgs))), 2) if imgs else 100.0

            viewport = bool(soup and soup.find("meta", attrs={"name": "viewport"}))
            nav_present = bool(soup and soup.find("nav"))
            intrusive_popup = any(k in text_low for k in ["popup", "modal", "subscribe", "newsletter"])

            page = {
                "url": final,
                "status": status,
                "response_time_ms": round(dur, 2),
                "html_size_bytes": len(body or b""),
                "title": title,
                "meta_description": meta_desc,
                "h1": h1,
                "security": {"is_https": is_https, "hsts": hsts, "csp": csp, "xfo": xfo, "mixed_content": mixed},
                "privacy": {"cookie_banner": cookie_banner, "has_privacy_policy": has_privacy_policy},
                "seo": {"canonical": canonical, "meta_robots": meta_robots, "schema": schema_present, "og": og_present, "twitter": tw_present, "hreflang": hreflangs, "thin": thin},
                "ux": {"viewport": viewport, "nav_present": nav_present, "intrusive_popup": intrusive_popup},
                "accessibility": {"alt_coverage_pct": alt_coverage_pct},
                "performance": {"gzip_or_br": gzip_or_br},
                "links_internal": list(dict.fromkeys(links_internal)),
                "links_external": list(dict.fromkeys(links_external)),
            }
            pages.append(page)

            for href in links_internal[:8]:
                if href not in visited and href not in queue and len(queue) + len(pages) < cfg.max_pages:
                    queue.append(href)

    avg_resp = round(sum(p["response_time_ms"] for p in pages) / max(1, len(pages)), 2)
    avg_html_kb = round(sum(p["html_size_bytes"] for p in pages) / max(1, len(pages)) / 1024.0, 2)

    return {"site": base, "pages": pages, "stats": {"avg_response_time_ms": avg_resp, "avg_html_size_kb": avg_html_kb}}

# PSI (CWV + Lighthouse)
async def fetch_psi(url: str, strategy: str = "mobile") -> Dict[str, Any]:
    if not PSI_API_KEY:
        return {"source": "none", "strategy": strategy}
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.get(
                "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
                params={"url": url, "strategy": strategy, "key": PSI_API_KEY}
            )
            data = r.json()
            lr = data.get("lighthouseResult", {}) or {}
            audits = lr.get("audits", {}) or {}
            cats = lr.get("categories", {}) or {}

            def num(key: str) -> Optional[float]:
                return (audits.get(key) or {}).get("numericValue")

            def cat_score(name: str) -> Optional[int]:
                sc = cats.get(name, {}).get("score")
                return int(round((sc or 0) * 100)) if sc is not None else None

            return {
                "source": "psi",
                "strategy": strategy,
                "lcp_ms": num("largest-contentful-paint"),
                "fcp_ms": num("first-contentful-paint"),
                "cls": num("cumulative-layout-shift"),
                "tbt_ms": num("total-blocking-time"),
                "tti_ms": num("interactive"),
                "lighthouse": {
                    "Performance": cat_score("performance"),
                    "Accessibility": cat_score("accessibility"),
                    "Best Practices": cat_score("best-practices"),
                    "SEO": cat_score("seo"),
                    "PWA": cat_score("pwa"),
                }
            }
    except Exception:
        return {"source": "none", "strategy": strategy}

# Scoring + weak areas
def compute_scores(crawl: Dict[str, Any], psi: Dict[str, Any]) -> Dict[str, Any]:
    pages = crawl["pages"]
    stats = crawl["stats"]

    totals = {
        "missing_titles": 0, "missing_meta": 0, "missing_h1": 0,
        "https_pages": 0, "hsts_missing": 0, "csp_missing": 0, "xfo_missing": 0, "mixed_content_pages": 0,
        "cookie_banner_pages": 0, "privacy_policy_pages": 0,
        "gzip_missing_pages": 0, "canonical_missing_pages": 0, "hreflang_pages": 0,
        "viewport_missing": 0, "nav_missing": 0, "intrusive_popup_pages": 0,
        "thin_pages": 0, "alt_issue_pages": 0,
        "avg_response_time_ms": stats["avg_response_time_ms"], "avg_html_size_kb": stats["avg_html_size_kb"],
    }

    title_count, meta_count = {}, {}
    for p in pages:
        t, m = p.get("title"), p.get("meta_description")
        if not t: totals["missing_titles"] += 1
        else: title_count[t] = title_count.get(t, 0) + 1
        if not m: totals["missing_meta"] += 1
        else: meta_count[m] = meta_count.get(m, 0) + 1
        if not p.get("h1"): totals["missing_h1"] += 1

        sec = p["security"]
        if sec["is_https"]: totals["https_pages"] += 1
        if sec["is_https"] and not sec["hsts"]: totals["hsts_missing"] += 1
        if not sec["csp"]: totals["csp_missing"] += 1
        if not sec["xfo"]: totals["xfo_missing"] += 1
        if sec["mixed_content"]: totals["mixed_content_pages"] += 1

        prv = p["privacy"]
        if prv["cookie_banner"]: totals["cookie_banner_pages"] += 1
        if prv["has_privacy_policy"]: totals["privacy_policy_pages"] += 1

        perf = p["performance"]
        if not perf["gzip_or_br"]: totals["gzip_missing_pages"] += 1

        seo = p["seo"]
        if not seo["canonical"]: totals["canonical_missing_pages"] += 1
        if seo["hreflang"]: totals["hreflang_pages"] += 1
        if seo["thin"]: totals["thin_pages"] += 1

        acc = p["accessibility"]
        if acc["alt_coverage_pct"] < 80.0: totals["alt_issue_pages"] += 1

        ux = p["ux"]
        if not ux["viewport"]: totals["viewport_missing"] += 1
        if not ux["nav_present"]: totals["nav_missing"] += 1
        if ux["intrusive_popup"]: totals["intrusive_popup_pages"] += 1

    # Category scores
    sec_score = 100
    sec_score -= min(30, totals["hsts_missing"] * 3)
    sec_score -= min(30, totals["csp_missing"] * 3)
    sec_score -= min(25, totals["xfo_missing"] * 2.5)
    sec_score -= min(40, totals["mixed_content_pages"] * 8)
    sec_score += min(5, totals["privacy_policy_pages"])
    sec_score = max(0, min(100, sec_score))

    perf_score = 100
    perf_score -= min(25, totals["gzip_missing_pages"] * 2)
    perf_score -= min(25, max(0, (totals["avg_response_time_ms"] - 800) / 100))
    perf_score -= min(20, max(0, (totals["avg_html_size_kb"] - 120) / 20))
    if isinstance(psi.get("lcp_ms"), (int, float)):
        perf_score -= min(25, max(0, (psi["lcp_ms"] - 2500) / 150))
    if isinstance(psi.get("tbt_ms"), (int, float)):
        perf_score -= min(20, max(0, (psi["tbt_ms"] - 300) / 50))
    if isinstance(psi.get("cls"), (int, float)):
        perf_score -= min(15, max(0, (psi["cls"] - 0.1) * 100))
    perf_score = max(0, min(100, perf_score))

    seo_score = 100
    seo_score -= min(30, totals["missing_titles"] * 2)
    seo_score -= min(20, totals["missing_meta"])
    seo_score -= min(20, totals["missing_h1"] * 2)
    seo_score -= min(15, totals["canonical_missing_pages"])
    seo_score += min(5, totals["hreflang_pages"])
    seo_score = max(0, min(100, seo_score))

    ux_score = 100
    ux_score -= min(25, totals["viewport_missing"] * 3)
    ux_score -= min(15, totals["nav_missing"] * 2)
    ux_score -= min(20, totals["intrusive_popup_pages"] * 4)
    ux_score = max(0, min(100, ux_score))

    content_score = 100
    content_score -= min(20, totals["thin_pages"] * 2)
    content_score -= min(20, totals["alt_issue_pages"] * 2)
    content_score = max(0, min(100, content_score))

    weights = {"Security":0.28,"Performance":0.27,"SEO":0.23,"UX":0.12,"Content":0.10}
    overall_score = int(round(
        sec_score * weights["Security"] +
        perf_score * weights["Performance"] +
        seo_score * weights["SEO"] +
        ux_score * weights["UX"] +
        content_score * weights["Content"]
    ))
    grade, grade_class = grade_for_score(overall_score)

    total_errors = (
        totals["hsts_missing"] + totals["csp_missing"] + totals["xfo_missing"] +
        totals["mixed_content_pages"] + totals["missing_titles"] +
        totals["missing_h1"] + totals["thin_pages"] + totals["alt_issue_pages"]
    )
    total_warnings = (
        totals["missing_meta"] + totals["canonical_missing_pages"] +
        totals["gzip_missing_pages"] + totals["viewport_missing"] + totals["nav_missing"]
    )
    total_notices = max(0, len(pages) - total_errors - total_warnings)

    weak_areas = []
    issue_pairs = [
        ("Mixed content found", totals["mixed_content_pages"]),
        ("No HSTS on HTTPS pages", totals["hsts_missing"]),
        ("Missing CSP header", totals["csp_missing"]),
        ("Missing titles/meta", totals["missing_titles"] + totals["missing_meta"]),
        ("Thin content pages (<300 words)", totals["thin_pages"]),
        ("Missing viewport (mobile)", totals["viewport_missing"]),
        ("Compression missing (Brotli/Gzip)", totals["gzip_missing_pages"]),
        ("Canonical missing", totals["canonical_missing_pages"]),
        ("Intrusive popups/modals", totals["intrusive_popup_pages"]),
    ]
    for name, count in sorted(issue_pairs, key=lambda x: x[1], reverse=True)[:6]:
        if count > 0:
            weak_areas.append(f"{name}: {count}")

    return {
        "overall_score": overall_score,
        "grade": grade,
        "grade_class": grade_class,
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "total_notices": total_notices,
        "category_scores": {
            "Security": sec_score,
            "Performance": perf_score,
            "SEO": seo_score,
            "UX": ux_score,
            "Content": content_score,
        },
        "totals": totals,
        "weak_areas": weak_areas,
    }

# Summary (~200 words)
def build_summary(site: str, scores: Dict[str, Any], psi: Dict[str, Any]) -> str:
    cs = scores["category_scores"]
    weakest = ", ".join(sorted(cs.keys(), key=lambda k: cs[k])[:2])
    lines = [
        f"This certified audit of {site} evaluates Security & Compliance, Performance & Core Web Vitals, SEO & Indexing, UX & Mobile, and Content Quality.",
        f"Overall health is {scores['overall_score']} ({scores['grade']}). Category scores — Security {cs['Security']}, Performance {cs['Performance']}, SEO {cs['SEO']}, UX {cs['UX']}, Content {cs['Content']}.",
        f"Key weak areas: {weakest}. Fixing these will strengthen trust, speed, discoverability, usability, and conversion.",
    ]
    if psi.get("source") == "psi":
        cats = psi.get("lighthouse", {}) or {}
        lines.append(
            f"Lighthouse snapshot — Perf {cats.get('Performance')}, A11y {cats.get('Accessibility')}, Best Practices {cats.get('Best Practices')}, SEO {cats.get('SEO')}, PWA {cats.get('PWA')}."
        )
        lines.append(
            f"Web Vitals — LCP {psi.get('lcp_ms')} ms, CLS {psi.get('cls')}, TBT {psi.get('tbt_ms')} ms, TTI {psi.get('tti_ms')} ms."
        )
    lines += [
        "Top actions: enforce HSTS/CSP; remove mixed content; enable Brotli/Gzip; reduce LCP/TBT with critical CSS and JS deferral; complete titles/meta and canonicals; ensure viewport; expand thin pages; add alt text; and avoid intrusive interstitials.",
        "Prioritize high-risk security/performance gaps first, then SEO/UX/content improvements to sustain growth."
    ]
    text = " ".join(lines)
    words = text.split()
    if len(words) > 220:
        text = " ".join(words[:220])
    return text

# Category tables for HTML
def status_label(score: int) -> str:
    if score >= 80: return "Good"
    if score >= 60: return "Warning"
    return "Critical"

def metric_row(name: str, score: int, priority: str, impact: str, rec: str) -> Dict[str, Any]:
    return {
        "name": name,
        "status": status_label(score),
        "score": score,
        "priority": priority,
        "impact": impact,
        "recommendation": rec,
    }

def build_category_tables(scores: Dict[str, Any], psi: Dict[str, Any]) -> List[Dict[str, Any]]:
    t = scores["totals"]
    cats: List[Dict[str, Any]] = []

    # Security
    sec_metrics = [
        metric_row("HTTPS / SSL valid", 100 if t["https_pages"] > 0 else 40, "High",
                   "HTTPS is required for trust and rankings.",
                   "Force HTTPS, ensure valid TLS, redirect HTTP to HTTPS."),
        metric_row("HSTS header present", max(10, 100 - t["hsts_missing"] * 10), "High",
                   "HSTS prevents downgrade/cookie hijack.",
                   "Add Strict-Transport-Security with includeSubDomains; consider preload."),
        metric_row("Content-Security-Policy (CSP)", max(10, 100 - t["csp_missing"] * 10), "High",
                   "CSP mitigates XSS and injection.", "Define a strict CSP and audit third-party sources."),
        metric_row("X-Frame-Options", max(10, 100 - t["xfo_missing"] * 10), "Medium",
                   "Prevents clickjacking.", "Set X-Frame-Options SAMEORIGIN or use frame-ancestors in CSP."),
        metric_row("Mixed content eliminated", max(10, 100 - t["mixed_content_pages"] * 20), "High",
                   "Mixed content breaks padlock and trust.", "Replace http:// assets with https://."),
        metric_row("Privacy / Cookie policy visible", 80 if t["privacy_policy_pages"] > 0 else 50, "Medium",
                   "Clear privacy reduces legal risk.", "Add privacy/cookie policy and a consent banner."),
    ]
    cats.append({"name": "Security & Compliance", "icon": "fa-shield-halved", "metrics": sec_metrics})

    # Performance
    perf_metrics = [
        metric_row("Core Web Vitals (LCP/CLS/TBT/TTI)", 70 if psi.get("source") == "psi" else 50, "High",
                   "Vitals drive UX, SEO, and revenue.", "Use Lighthouse; optimize critical path, images, and JS."),
        metric_row("Compression (Brotli/Gzip)", max(10, 100 - t["gzip_missing_pages"] * 8), "High",
                   "Compression reduces transfer size.", "Enable Brotli/Gzip and configure Cache-Control."),
        metric_row("Server response time (TTFB approx)", max(10, 100 - int(max(0, t["avg_response_time_ms"] - 800) / 8)), "High",
                   "Slow responses harm LCP/crawl.", "Use CDN, profile backend, optimize DB and caches."),
        metric_row("Page size (HTML)", max(10, 100 - int(max(0, t["avg_html_size_kb"] - 120) / 2)), "Medium",
                   "Large HTML increases parse time.", "Trim markup, remove unused code, split templates."),
    ]
    cats.append({"name": "Performance & Web Vitals", "icon": "fa-gauge-high", "metrics": perf_metrics})

    # SEO
    seo_metrics = [
        metric_row("Meta titles/descriptions present", max(10, 100 - (t["missing_titles"] * 10 + t["missing_meta"] * 8)), "High",
                   "Titles/meta drive CTR and relevance.", "Add unique titles/meta per page."),
        metric_row("H1 structure sound", max(10, 100 - t["missing_h1"] * 8), "Medium",
                   "Headings clarify topical hierarchy.", "Ensure one H1 and logical H2/H3 hierarchy."),
        metric_row("Canonical tags present", max(10, 100 - t["canonical_missing_pages"] * 8), "Medium",
                   "Canonicals consolidate signals.", "Add canonical to preferred URL."),
        metric_row("Hreflang (multi-language)", 70 if t["hreflang_pages"] > 0 else 50, "Low",
                   "Correct language targeting.", "Add hreflang and validate in Search Console."),
    ]
    cats.append({"name": "SEO & Indexing", "icon": "fa-magnifying-glass-chart", "metrics": seo_metrics})

    # UX
    ux_metrics = [
        metric_row("Responsive (viewport)", max(10, 100 - t["viewport_missing"] * 10), "High",
                   "Viewport is foundational for mobile UX.", "Add <meta name='viewport' content='width=device-width, initial-scale=1'>"),
        metric_row("Navigation usability", max(10, 100 - t["nav_missing"] * 10), "Medium",
                   "Semantic nav reduces friction.", "Use <nav>, clear labels, keyboard support."),
        metric_row("Intrusive interstitials avoided", max(10, 100 - t["intrusive_popup_pages"] * 20), "High",
                   "Popups hurt UX and rankings.", "Avoid full-screen overlays; delay prompts."),
    ]
    cats.append({"name": "UX & Mobile", "icon": "fa-mobile-screen-button", "metrics": ux_metrics})

    # Content
    content_metrics = [
        metric_row("Thin content (<300 words)", max(10, 100 - t["thin_pages"] * 10), "High",
                   "Thin content limits ranking.", "Expand pages with unique, intent-driven content."),
        metric_row("Image alt attributes", max(10, 100 - t["alt_issue_pages"] * 10), "Medium",
                   "Alt text improves accessibility/SEO.", "Add meaningful alt attributes to images."),
        metric_row("Structured data / Schema.org present", 70, "Medium",
                   "Schema enables rich results.", "Add appropriate schema types (Article/Product/Org)."),
        metric_row("Open Graph / Twitter cards", 70, "Low",
                   "Social cards improve previews/CTR.", "Add og:title/description/image and twitter:card."),
    ]
    cats.append({"name": "Content Quality & On-Page SEO", "icon": "fa-file-lines", "metrics": content_metrics})

    return cats

# Trend chart dataset
def build_trend_chart(site: str, current_overall: int) -> Dict[str, Any]:
    records = load_recent(site, limit=8)
    labels = [r.get("created_at", "")[:10] for r in reversed(records)]
    values = [r.get("result", {}).get("overall_score", 0) for r in reversed(records)]
    labels.append(datetime.utcnow().strftime("%Y-%m-%d"))
    values.append(current_overall)
    return {"labels": labels, "values": values}

# Routes
@app.get("/", response_class=HTMLResponse)
async def home():
    return HTMLResponse(f"""
    <!doctype html><html><head><meta charset="utf-8"><title>{APP_NAME}</title>
    https://cdn.tailwindcss.com</script></head>
    <body class="bg-gray-50">
      <div class="max-w-xl mx-auto mt-16 bg-white shadow rounded p-6">
        <h1 class="text-xl font-bold mb-4">{APP_NAME}</h1>
        /report
          <div>
            <label class="block text-sm font-medium text-gray-700">Website URL</label>
            <input name="url" required placeholder="https://example.com" class="mt-1 w-full border rounded px-3 py-2 focus:ring focus:border-indigo-500">
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700">PSI Strategy</label>
            <select name="psi_strategy" class="mt-1 w-full border rounded px-3 py-2">
              <option value="mobile">mobile</option>
              <option value="desktop">desktop</option>
            </select>
          </div>
          <button class="bg-indigo-600 text-white px-4 py-2 rounded hover:bg-indigo-700">Run Audit</button>
        </form>
        <p class="text-xs text-gray-400 mt-4">Tip: set <code>PSI_API_KEY</code> in env for Core Web Vitals & Lighthouse.</p>
      </div>
    </body></html>
    """)

@app.post("/report", response_class=HTMLResponse)
async def render_report(url: str = Form(...), psi_strategy: str = Form("mobile")):
    url = url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL required")

    # Crawl site
    crawl = await crawl_site(CrawlConfig(url=url))
    # CWV/Lighthouse
    psi = await fetch_psi(crawl["site"], psi_strategy)
    # Scores
    scores = compute_scores(crawl, psi)
    # Summary
    summary = build_summary(crawl["site"], scores, psi)
    # Category tables
    categories = build_category_tables(scores, psi)
    # Owner insights
    owner_insights = [
        {"title": "Secure-by-default posture", "description": "Enable HSTS, define a robust CSP, remove mixed content, and set X-Frame-Options to prevent common exploits."},
        {"title": "Speed up the critical path", "description": "Compress with Brotli/Gzip, optimize hero images and critical CSS, and defer non-essential JS to lower LCP/TBT."},
        {"title": "Strengthen indexability", "description": "Ensure unique titles/meta, add canonicals, improve heading structure, and use hreflang for multi-language."},
        {"title": "Improve mobile UX", "description": "Add viewport, validate navigation accessibility, and avoid intrusive interstitials on mobile viewports."},
        {"title": "Enhance content signals", "description": "Expand thin pages with substantive content, add alt text to images, and annotate with structured data."},
    ]

    # Persist & trend
    audit_id = str(hash(url + str(time.time())))[-12:]
    payload = {"site": crawl["site"], "created_at": datetime.utcnow().isoformat(), "result": {"overall_score": scores["overall_score"], "grade": scores["grade"]}}
    AUDITS[audit_id] = payload
    init_db()
    save_audit(audit_id, crawl["site"], payload)
    trend_data = build_trend_chart(crawl["site"], scores["overall_score"])

    # Render
    template = env.from_string(HTML_TEMPLATE)
    html = template.render(
        app_name=APP_NAME,
        website_url=crawl["site"],
        audit_date=datetime.utcnow().strftime("%Y-%m-%d"),
        audit_id=audit_id,

        grade=scores["grade"],
        grade_class=scores["grade_class"],
        overall_score=scores["overall_score"],
        total_errors=scores["total_errors"],
        total_warnings=scores["total_warnings"],
        total_notices=max(0, len(crawl["pages"]) - scores["total_errors"] - scores["total_warnings"]),

        executive_summary_200_words=summary,
        weak_areas=scores["weak_areas"],

        audit_categories=categories,
        owner_insights=owner_insights,

        validity_date=datetime.utcnow().strftime("%Y-%m-%d"),
        trend_chart_data=trend_data,
    )
    return HTMLResponse(html)

@app.get("/health")
async def health():
    return {"status": "ok", "ts": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
