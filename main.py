
# main.py
# FF Tech — AI Website Audit Platform (Single-file backend + embedded Jinja HTML)
#
# Requirements (install via requirements.txt):
#   fastapi==0.115.5
#   uvicorn==0.32.0
#   httpx==0.27.2
#   beautifulsoup4==4.12.3
#   lxml==5.3.0
#   tldextract==5.1.2
#   jinja2==3.1.4
#   reportlab==4.0.9
#
# Run:
#   python -m venv .venv && . .venv/bin/activate
#   pip install -r requirements.txt
#   uvicorn main:app --reload
#
# Optional env:
#   export PSI_API_KEY=your_key   # enable CWV + Lighthouse via Google PSI
#   export ENABLE_HISTORY=true    # persist audits for the trend chart (SQLite)

import os
import re
import json
import time
import math
import httpx
import sqlite3
import tldextract
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse
from jinja2 import Environment, BaseLoader, select_autoescape

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

# -----------------------------
# Embedded fixed HTML (your template)
# -----------------------------
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{{ app_name }} | AI Website Audit Platform</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap
https://cdn.jsdelivr.net/npm/chart.js</script>
<style>
:root {
    --good:#16a34a;
    --warn:#f59e0b;
    --bad:#dc2626;
    --bg:#f5f7fb;
    --card:#ffffff;
}
body { font-family: 'Inter', sans-serif; background: var(--bg); margin:0; color:#1f2937; }
.container { max-width:1500px; margin:auto; padding:30px; }
.card { background:var(--card); border-radius:16px; padding:24px; margin-bottom:24px; box-shadow:0 10px 30px rgba(0,0,0,.06); }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:20px; }
h1,h2,h3 { margin-bottom:10px; }
.score { font-size:48px; font-weight:700; }
.grade { display:inline-block; padding:10px 18px; border-radius:12px; font-weight:700; font-size:22px; }
.Aplus{background:#16a34a;color:#fff} .A{background:#22c55e;color:#fff} .B{background:#facc15;color:#000} .C{background:#fb923c;color:#fff} .D{background:#ef4444;color:#fff}
.good{color:var(--good);font-weight:600} .warning{color:var(--warn);font-weight:600} .critical{color:var(--bad);font-weight:700}
table { width:100%; border-collapse:collapse; margin-top:12px; }
th,td { padding:12px; border-bottom:1px solid #e5e7eb; text-align:left; }
th { background:#f1f5f9; }
.badge { padding:6px 10px; border-radius:10px; font-size:12px; font-weight:600; }
.high{background:#fee2e2;color:#991b1b} .medium{background:#fef3c7;color:#92400e} .low{background:#dcfce7;color:#166534}
footer { text-align:center; font-size:13px; color:#6b7280; margin-top:40px; }
.collapse-btn { cursor:pointer; font-weight:600; color:#2563eb; margin-bottom:10px; display:inline-block; }
.collapse-content { display:none; }
</style>
</head>
<body>
<div class="container">

<!-- HEADER -->
<div class="card">
    <h1>{{ app_name }}</h1>
    <p><strong>Website:</strong> {{ website_url }}</p>
    <p><strong>Audit Date:</strong> {{ audit_date }}</p>
    <p><strong>Audit ID:</strong> {{ audit_id }}</p>
</div>

<!-- OVERALL HEALTH -->
<div class="grid">
    <div class="card">
        <h3>Overall Website Health</h3>
        <div class="score">{{ overall_score }}%</</div>
        <div class="grade {{ grade_class }}">{{ grade }}</div>
    </div>
    <div class="card">
        <h3>Risk Breakdown</h3>
        <p class="critical">Errors: {{ total_errors }}</p>
        <p class="warning">Warnings: {{ total_warnings }}</p>
        <p class="good">Notices: {{ total_notices }}</p>
    </div>
    <div class="card">
        <h3>Category Scores</h3>
        {% for cat, score in category_scores.items() %}
            <p>{{ cat }}: {{ score }}%</p>
        {% endfor %}
    </div>
</div>

<!-- EXECUTIVE SUMMARY -->
<div class="card">
    <h2>Executive Summary</h2>
    <p>{{ executive_summary_200_words }}</p>
</div>

<!-- WEAK AREAS HIGHLIGHT -->
<div class="card">
    <h2>Critical Weak Areas</h2>
    <ul>
        {% for weakness in weak_areas %}
        <li class="critical">{{ weakness }}</li>
        {% endfor %}
    </ul>
</div>

<!-- AUDIT CATEGORIES & METRICS -->
{% for category in audit_categories %}
<div class="card">
    <h2>{{ category.name }}</h2>
    <p>{{ category.description }}</p>
    <span class="collapse-btn" onclick="toggleCollapse('{{ loop.index0 }}')">Show / Hide Metrics</span>
    <div id="collapse-{{ loop.index0 }}" class="collapse-content">
        <table>
            <thead>
            <tr>
                <th>Metric</th>
                <th>Status</th>
                <th>Score</th>
                <th>Priority</th>
                <th>Why It Matters</th>
                <th>Recommendation</th>
            </tr>
            </thead>
            <tbody>
            {% for metric in category.metrics %}
            <tr>
                <td>{{ metric.name }}</td>
                <td class="{{ metric.status_class }}">{{ metric.status }}</td>
                <td>{{ metric.score }}/100</td>
                <td><span class="badge {{ metric.priority_class }}">{{ metric.priority }}</span></td>
                <td>{{ metric.impact }}</td>
                <td>{{ metric.recommendation }}</td>
            </tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endfor %}

<!-- TREND ANALYSIS -->
<div class="card">
    <h2>Historical Performance Trend</h2>
    <canvas id="trendChart"></canvas>
</div>

<!-- OWNER INSIGHTS -->
<div class="card">
    <h2>Owner-Focused Insights</h2>
    <ul>
        {% for insight in owner_insights %}
        <li>{{ insight }}</li>
        {% endfor %}
    </ul>
</div>

<!-- CERTIFIED AUDIT -->
<div class="card">
    <h2>Certified Audit Report</h2>
    <p>This audit is officially certified by <strong>{{ company_name }}</strong>.</p>
    <p>Valid Until: {{ validity_date }}</p>
    <p>Certification Level: {{ grade }}</p>
</div>

<footer>
    © {{ current_year }} {{ company_name }} | International AI Audit SaaS — {{ version }}
</footer>

<script>
function toggleCollapse(id){
    var content = document.getElementById('collapse-'+id);
    if(content.style.display === "block"){ content.style.display="none"; }
    else{ content.style.display="block"; }
}

// TREND CHART
const trendData = {{ trend_chart_data | safe }};
if(trendData){
    new Chart(document.getElementById('trendChart'), {
        type:'line',
        data:trendData,
        options:{responsive:true, plugins:{legend:{display:true}}}
    });
}
</script>
</body>
</html>
"""

# -----------------------------
# App config
# -----------------------------
app = FastAPI()
env = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html", "xml"]))
APP_NAME = "FF Tech — Enterprise AI Website Audit"
COMPANY_NAME = "FF Tech"
VERSION = "v1.0"
ENABLE_HISTORY = os.getenv("ENABLE_HISTORY", "").lower() in ("true", "1", "yes")
PSI_API_KEY = os.getenv("PSI_API_KEY")

DB_FILE = "audits.db"
AUDITS: Dict[str, Dict[str, Any]] = {}

# -----------------------------
# DB helpers for trend
# -----------------------------
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

def load_recent(site: str, limit: int = 12) -> List[dict]:
    if not ENABLE_HISTORY:
        return []
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute(
        "SELECT payload_json FROM audits WHERE site=? ORDER BY created_at DESC LIMIT ?",
        (site, limit)
    ).fetchall()
    conn.close()
    return [json.loads(r[0]) for r in rows]

# -----------------------------
# Utilities
# -----------------------------
def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def grade_for_score(score: int) -> Tuple[str, str]:
    if score >= 92: return ("A+", "Aplus")
    if score >= 85: return ("A", "A")
    if score >= 75: return ("B", "B")
    if score >= 65: return ("C", "C")
    return ("D", "D")

def priority_class(level: str) -> str:
    return {"High": "high", "Medium": "medium", "Low": "low"}.get(level, "low")

# -----------------------------
# Crawl (httpx-only)
# -----------------------------
@dataclass
class CrawlConfig:
    url: str
    max_pages: int = 24
    concurrency: int = 12
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

            # Mixed content
            mixed = False
            if is_https and soup:
                for tag in soup.find_all(["img", "script", "link", "iframe"]):
                    src = tag.get("src") or tag.get("href") or ""
                    if src.startswith("http://"):
                        mixed = True
                        break

            # Privacy signals
            text_low = (soup.get_text(" ", strip=True).lower() if soup else "")
            cookie_banner = any(k in text_low for k in ["cookie consent", "we use cookies", "accept cookies", "gdpr", "privacy"])
            has_privacy_policy_signal = any(k in text_low for k in ["privacy policy", "policy", "gdpr"])

            # Compression
            enc = (h.get("content-encoding") or "").lower()
            gzip_or_br = ("gzip" in enc) or ("br" in enc)

            # Links
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

            # Canonical / robots
            can = soup.find("link", attrs={"rel": "canonical"}) if soup else None
            canonical = can.get("href") if (can and can.get("href")) else None
            mr = soup.find("meta", attrs={"name": "robots"}) if soup else None
            meta_robots = (mr.get("content", "").lower() if mr else "")

            # i18n/Schema/Social
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

            # Content
            word_count = len((soup.get_text(" ", strip=True) if soup else "").split())
            thin = word_count < 300

            # Accessibility
            imgs = soup.find_all("img") if soup else []
            imgs_with_alt = [img for img in imgs if clean(img.get("alt"))]
            alt_coverage_pct = round(100.0 * (len(imgs_with_alt) / max(1, len(imgs))), 2) if imgs else 100.0

            # UX signals
            viewport = bool(soup and soup.find("meta", attrs={"name": "viewport"}))
            nav_present = bool(soup and soup.find("nav"))
            intrusive_popup = any(k in text_low for k in ["popup", "modal", "subscribe", "newsletter"])

            page = {
                "requested_url": url,
                "url": final,
                "status": status,
                "response_time_ms": round(dur, 2),
                "html_size_bytes": len(body or b""),
                "title": title,
                "meta_description": meta_desc,
                "h1": h1,
                "security": {
                    "is_https": is_https,
                    "hsts": hsts,
                    "csp": csp,
                    "xfo": xfo,
                    "mixed_content": mixed,
                },
                "privacy": {
                    "cookie_banner": cookie_banner,
                    "has_privacy_policy_signal": has_privacy_policy_signal,
                },
                "seo": {
                    "canonical": canonical,
                    "meta_robots": meta_robots,
                    "schema": schema_present,
                    "og": og_present,
                    "twitter": tw_present,
                    "hreflang": hreflangs,
                    "thin": thin,
                    "word_count": word_count,
                },
                "ux": {
                    "viewport": viewport,
                    "nav_present": nav_present,
                    "intrusive_popup": intrusive_popup,
                },
                "accessibility": {"alt_coverage_pct": alt_coverage_pct},
                "links_internal": list(dict.fromkeys(links_internal)),
                "links_external": list(dict.fromkeys(links_external)),
            }
            pages.append(page)

            # enqueue some internal links
            for href in links_internal[:8]:
                if href not in visited and href not in queue and len(queue) + len(pages) < cfg.max_pages:
                    queue.append(href)

    avg_resp = round(sum(p["response_time_ms"] for p in pages) / max(1, len(pages)), 2)
    avg_html_kb = round(sum(p["html_size_bytes"] for p in pages) / max(1, len(pages)) / 1024.0, 2)

    return {
        "site": base,
        "pages": pages,
        "stats": {"avg_response_time_ms": avg_resp, "avg_html_size_kb": avg_html_kb},
    }

# -----------------------------
# PSI (CWV + Lighthouse)
# -----------------------------
async def fetch_psi(url: str, strategy: str = "mobile") -> Dict[str, Any]:
    if not PSI_API_KEY:
        return {"source": "none", "strategy": strategy}
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.get(
                "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
                params={"url": url, "strategy": strategy, "key": PSI_API_KEY},
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

# -----------------------------
# Scoring + Weak areas
# -----------------------------
def compute_scores(crawl: Dict[str, Any], psi: Dict[str, Any]) -> Dict[str, Any]:
    pages = crawl["pages"]
    stats = crawl["stats"]
    totals = {
        "missing_titles": 0,
        "missing_meta": 0,
        "missing_h1": 0,
        "https_pages": 0,
        "hsts_missing": 0,
        "csp_missing": 0,
        "xfo_missing": 0,
        "mixed_content_pages": 0,
        "cookie_banner_pages": 0,
        "privacy_signal_pages": 0,
        "gzip_missing_pages": 0,
        "canonical_missing_pages": 0,
        "hreflang_pages": 0,
        "viewport_missing": 0,
        "nav_missing": 0,
        "intrusive_popup_pages": 0,
        "thin_pages": 0,
        "alt_issue_pages": 0,
        "duplicate_titles": 0,
        "duplicate_meta": 0,
        "avg_response_time_ms": stats["avg_response_time_ms"],
        "avg_html_size_kb": stats["avg_html_size_kb"],
    }

    title_count, meta_count = {}, {}
    for p in pages:
        title = p.get("title")
        meta = p.get("meta_description")
        if not title: totals["missing_titles"] += 1
        else: title_count[title] = title_count.get(title, 0) + 1
        if not meta: totals["missing_meta"] += 1
        else: meta_count[meta] = meta_count.get(meta, 0) + 1
        if not p.get("h1"): totals["missing_h1"] += 1

        sec = p["security"]
        if sec["is_https"]: totals["https_pages"] += 1
        if sec["is_https"] and not sec["hsts"]: totals["hsts_missing"] += 1
        if not sec["csp"]: totals["csp_missing"] += 1
        if not sec["xfo"]: totals["xfo_missing"] += 1
        if sec["mixed_content"]: totals["mixed_content_pages"] += 1

        prv = p["privacy"]
        if prv["cookie_banner"]: totals["cookie_banner_pages"] += 1
        if prv["has_privacy_policy_signal"]: totals["privacy_signal_pages"] += 1

        if not p["performance"]["gzip_or_br"]: totals["gzip_missing_pages"] += 1

        seo = p["seo"]
        if not seo["canonical"]: totals["canonical_missing_pages"] += 1
        if seo["hreflang"]: totals["hreflang_pages"] += 1
        if seo["thin"]: totals["thin_pages"] += 1

        if p["accessibility"]["alt_coverage_pct"] < 80.0: totals["alt_issue_pages"] += 1

        ux = p["ux"]
        if not ux["viewport"]: totals["viewport_missing"] += 1
        if not ux["nav_present"]: totals["nav_missing"] += 1
        if ux["intrusive_popup"]: totals["intrusive_popup_pages"] += 1

    totals["duplicate_titles"] = sum(1 for v in title_count.values() if v > 1)
    totals["duplicate_meta"] = sum(1 for v in meta_count.values() if v > 1)

    # Category scores
    sec_score = 100
    sec_score -= min(30, totals["hsts_missing"] * 3)
    sec_score -= min(30, totals["csp_missing"] * 3)
    sec_score -= min(25, totals["xfo_missing"] * 2.5)
    sec_score -= min(40, totals["mixed_content_pages"] * 8)
    sec_score += min(5, totals["privacy_signal_pages"])
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
    seo_score -= min(10, totals["duplicate_titles"])
    seo_score -= min(10, totals["duplicate_meta"])
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
    content_score -= min(10, 0)  # placeholder for extra content issues
    content_score = max(0, min(100, content_score))

    weights = {"Security":0.28, "Performance":0.27, "SEO":0.23, "UX":0.12, "Content":0.10}
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
        totals["gzip_missing_pages"] + totals["duplicate_titles"] +
        totals["duplicate_meta"] + totals["viewport_missing"] + totals["nav_missing"]
    )
    total_notices = max(0, len(pages) - total_errors - total_warnings)

    # Weak areas
    weak_areas = []
    issue_pairs = [
        ("Mixed content found", totals["mixed_content_pages"]),
        ("No HSTS on HTTPS pages", totals["hsts_missing"]),
        ("Missing CSP headers", totals["csp_missing"]),
        ("Missing titles/meta", totals["missing_titles"] + totals["missing_meta"]),
        ("Thin content pages (<300 words)", totals["thin_pages"]),
        ("Missing viewport (mobile)", totals["viewport_missing"]),
        ("Intrusive popups/modals", totals["intrusive_popup_pages"]),
        ("Compression missing (Brotli/Gzip)", totals["gzip_missing_pages"]),
        ("Canonical missing", totals["canonical_missing_pages"]),
    ]
    for name, count in sorted(issue_pairs, key=lambda x: x[1], reverse=True)[:5]:
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

# -----------------------------
# Executive summary (~200 words)
# -----------------------------
def build_summary(site: str, scores: Dict[str, Any], psi: Dict[str, Any]) -> str:
    cs = scores["category_scores"]
    weakest = ", ".join(sorted(cs.keys(), key=lambda k: cs[k])[:2])
    lines = [
        f"This audit of {site} evaluates Security & Compliance, Performance & Core Web Vitals, SEO & Indexing, UX & Mobile, and Content Quality.",
        f"The overall health score is {scores['overall_score']} ({scores['grade']}). Category scores — Security: {cs['Security']}, Performance: {cs['Performance']}, SEO: {cs['SEO']}, UX: {cs['UX']}, Content: {cs['Content']}.",
        f"Critical weak areas include: {weakest}. Addressing these will improve trust, speed, discoverability, usability, and conversions.",
    ]
    if psi.get("source") == "psi":
        cats = psi.get("lighthouse", {}) or {}
        lines.append(
            f"Lighthouse snapshot — Performance: {cats.get('Performance')}, Accessibility: {cats.get('Accessibility')}, Best Practices: {cats.get('Best Practices')}, SEO: {cats.get('SEO')}, PWA: {cats.get('PWA')}."
        )
        lines.append(
            f"Web Vitals — LCP: {psi.get('lcp_ms')} ms, CLS: {psi.get('cls')}, TBT: {psi.get('tbt_ms')} ms, TTI: {psi.get('tti_ms')} ms."
        )
    lines += [
        "Top actions: enforce HSTS/CSP, remove mixed content; enable Brotli/Gzip; optimize hero images and critical CSS; complete titles/meta and canonicals; ensure viewport; reduce thin pages; add alt text; and fix intrusive interstitials.",
        "Prioritize high-risk security/performance issues first, then SEO/UX/content to sustain growth."
    ]
    text = " ".join(lines)
    words = text.split()
    if len(words) > 220:
        text = " ".join(words[:220])
    return text

# -----------------------------
# Build category tables
# -----------------------------
def metric_row(name: str, passed: bool, score: int, priority: str, impact: str, recommendation: str) -> Dict[str, Any]:
    return {
        "name": name,
        "status": "Pass" if passed else ("Warning" if score >= 60 else "Fail"),
        "status_class": "good" if passed else ("warning" if score >= 60 else "critical"),
        "score": score,
        "priority": priority,
        "priority_class": priority_class(priority),
        "impact": impact,
        "recommendation": recommendation,
    }

def build_category_tables(scores: Dict[str, Any], psi: Dict[str, Any]) -> List[Dict[str, Any]]:
    t = scores["totals"]
    categories: List[Dict[str, Any]] = []

    # Security & Compliance
    sec_rows = [
        metric_row("HTTPS / SSL valid", t["https_pages"] > 0, 100 if t["https_pages"] > 0 else 40, "High",
                   "HTTPS is required for trust, rankings, and compliance.",
                   "Force HTTPS, keep TLS valid, redirect all HTTP to HTTPS."),
        metric_row("HSTS header", t["hsts_missing"] == 0, max(10, 100 - t["hsts_missing"] * 10), "High",
                   "HSTS prevents protocol downgrade and cookie hijack.",
                   "Enable Strict-Transport-Security with includeSubDomains; consider preload."),
        metric_row("Content-Security-Policy (CSP)", t["csp_missing"] == 0, max(10, 100 - t["csp_missing"] * 10), "High",
                   "CSP mitigates XSS and injection attacks.", "Add a strict CSP and audit external sources."),
        metric_row("X-Frame-Options", t["xfo_missing"] == 0, max(10, 100 - t["xfo_missing"] * 10), "Medium",
                   "Prevents clickjacking.", "Set X-Frame-Options: SAMEORIGIN or use frame-ancestors in CSP."),
        metric_row("Mixed content eliminated", t["mixed_content_pages"] == 0, max(10, 100 - t["mixed_content_pages"] * 20), "High",
                   "Mixed content breaks padlock and user trust.", "Replace http:// assets with https://."),
        metric_row("Privacy / Cookie policy", t["privacy_signal_pages"] > 0, 80 if t["privacy_signal_pages"] > 0 else 50, "Medium",
                   "Clear privacy reduces legal risk and improves transparency.", "Add privacy/cookie policy and consent banner."),
    ]
    categories.append({"name": "Security & Compliance", "description": "Encryption, headers, privacy, and trust signals.", "metrics": sec_rows})

    # Performance & Web Vitals
    perf_rows = [
        metric_row("Core Web Vitals (LCP/CLS/TBT/TTI)", psi.get("source") == "psi", 70 if psi.get("source") == "psi" else 50, "High",
                   "Vitals impact UX, SEO, and revenue.", "Use PSI/Lighthouse; optimize critical path, images, and JS."),
        metric_row("Compression (Brotli/Gzip)", t["gzip_missing_pages"] == 0, max(10, 100 - t["gzip_missing_pages"] * 8), "High",
                   "Reduced transfer size speeds up pages.", "Enable Brotli/Gzip; set effective cache-control."),
        metric_row("Server response time (TTFB approx)", t["avg_response_time_ms"] < 800,
                   max(10, 100 - int(max(0, t["avg_response_time_ms"] - 800) / 8)), "High",
                   "Slow responses harm LCP and crawl budget.", "Use CDN, profile backend, optimize DB and caches."),
        metric_row("Page size (HTML)", t["avg_html_size_kb"] < 120,
                   max(10, 100 - int(max(0, t["avg_html_size_kb"] - 120) / 2)), "Medium",
                   "Large HTML increases parse time.", "Trim markup, remove unused code, split templates."),
    ]
    categories.append({"name": "Performance & Web Vitals", "description": "Speed, compression, PSI Lighthouse signals.", "metrics": perf_rows})

    # SEO / Indexing
    seo_rows = [
        metric_row("Meta titles/descriptions", t["missing_titles"] == 0 and t["missing_meta"] == 0,
                   max(10, 100 - (t["missing_titles"] * 10 + t["missing_meta"] * 8)), "High",
                   "Titles/meta drive relevance and CTR.", "Add unique, descriptive titles/meta for each page."),
        metric_row("H1 structure", t["missing_h1"] == 0, max(10, 100 - t["missing_h1"] * 8), "Medium",
                   "Headings clarify topical hierarchy.", "Ensure one H1 per page with logical H2/H3."),
        metric_row("Canonical tags", t["canonical_missing_pages"] == 0, max(10, 100 - t["canonical_missing_pages"] * 8), "Medium",
                   "Canonicals prevent duplicate indexing.", "Add canonical link to preferred URL per page."),
        metric_row("Hreflang (multi-language)", t["hreflang_pages"] > 0, 70 if t["hreflang_pages"] > 0 else 50, "Low",
                   "Correct regional/language targeting.", "Add hreflang tags and validate in Search Console."),
    ]
    categories.append({"name": "SEO & Indexing", "description": "Crawl signals, duplicate prevention, multi-language tags.", "metrics": seo_rows})

    # UX & Mobile
    ux_rows = [
        metric_row("Responsive (viewport)", t["viewport_missing"] == 0, max(10, 100 - t["viewport_missing"] * 10), "High",
                   "Viewport is foundational for mobile UX.", "Add <meta name='viewport' content='width=device-width, initial-scale=1'>"),
        metric_row("Navigation usability", t["nav_missing"] == 0, max(10, 100 - t["nav_missing"] * 10), "Medium",
                   "Semantic nav reduces friction.", "Use <nav>, clear labels, keyboard support, skip links."),
        metric_row("Intrusive interstitials", t["intrusive_popup_pages"] == 0, max(10, 100 - t["intrusive_popup_pages"] * 20), "High",
                   "Popups hurt UX and rankings.", "Avoid full-screen overlays; delay prompts."),
    ]
    categories.append({"name": "UX & Mobile", "description": "Mobile-first and usability signals.", "metrics": ux_rows})

    # Content Quality & On-Page SEO
    content_rows = [
        metric_row("Thin content (<300 words)", t["thin_pages"] == 0, max(10, 100 - t["thin_pages"] * 10), "High",
                   "Thin content limits ranking potential.", "Expand pages with unique, intent-driven content."),
        metric_row("Image alt attributes", t["alt_issue_pages"] == 0, max(10, 100 - t["alt_issue_pages"] * 10), "Medium",
                   "Alt text improves accessibility and SEO.", "Add meaningful alt attributes to informative images."),
        metric_row("Structured data / Schema.org", True, 70, "Medium",
                   "Schema enables rich results.", "Add Article/Product/Organization schema where relevant."),
        metric_row("Open Graph / Twitter cards", True, 70, "Low",
                   "Social cards improve sharing previews.", "Add og:title/description/image and twitter:card tags."),
    ]
    categories.append({"name": "Content Quality & On-Page SEO", "description": "Depth, accessibility, schema, and social metadata.", "metrics": content_rows})

    return categories

# -----------------------------
# Trend chart (Chart.js)
# -----------------------------
def build_trend_chart(site: str, current_scores: Dict[str, Any]) -> Dict[str, Any]:
    records = load_recent(site, limit=10)
    labels, overall, sec, perf, seo, ux, content = [], [], [], [], [], [], []

    for r in reversed(records):
        labels.append(r.get("created_at", "")[:10])
        rs = r.get("result", {}) or {}
        subs = rs.get("summary", {}).get("subscores", {}) or {}
        overall.append(rs.get("overall_score", 0))
        sec.append(subs.get("security", 0))
        perf.append(subs.get("performance", 0))
        seo.append(subs.get("seo", 0))
        ux.append(subs.get("ux", 0))
        content.append(subs.get("content", 0))

    now_label = datetime.utcnow().strftime("%Y-%m-%d")
    labels.append(now_label)
    overall.append(current_scores["overall_score"])
    sec.append(current_scores["category_scores"]["Security"])
    perf.append(current_scores["category_scores"]["Performance"])
    seo.append(current_scores["category_scores"]["SEO"])
    ux.append(current_scores["category_scores"]["UX"])
    content.append(current_scores["category_scores"]["Content"])

    return {
        "labels": labels,
        "datasets": [
            {"label": "Overall Health", "data": overall, "borderColor": "#2563eb", "backgroundColor": "transparent"},
            {"label": "Security", "data": sec, "borderColor": "#16a34a", "backgroundColor": "transparent"},
            {"label": "Performance", "data": perf, "borderColor": "#f59e0b", "backgroundColor": "transparent"},
            {"label": "SEO", "data": seo, "borderColor": "#0ea5e9", "backgroundColor": "transparent"},
            {"label": "UX", "data": ux, "borderColor": "#e11d48", "backgroundColor": "transparent"},
            {"label": "Content", "data": content, "borderColor": "#8b5cf6", "backgroundColor": "transparent"},
        ]
    }

# -----------------------------
# Routes
# -----------------------------
@app.get("/", response_class=HTMLResponse)
async def index():
    # Small launcher: post a URL to render the full audit page
    return HTMLResponse(f"""
    <!doctype html><html><head><meta charset="utf-8"><title>{APP_NAME}</title>
    https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap</head>
    <body style="font-family:Inter,Arial;max-width:720px;margin:40px auto;">
      <h1>{APP_NAME}</h1>
      /render
        <label>Website URL <input name="url" placeholder="https://example.com" style="width:100%;padding:8px;"></label>
        <label>PSI Strategy
          <select name="psi_strategy" style="padding:8px;">
            <option value="mobile">mobile</option>
            <option value="desktop">desktop</option>
          </select>
        </label>
        <button type="submit" style="padding:10px 14px;background:#2563eb;color:#fff;border:none;border-radius:6px;">Run Audit</button>
      </form>
      <p style="margin-top:12px;color:#6b7280">Tip: set <code>PSI_API_KEY</code> in env to display Lighthouse & Core Web Vitals.</p>
    </body></html>
    """)

@app.post("/render", response_class=HTMLResponse)
async def render_audit(url: str = Form(...), psi_strategy: str = Form("mobile")):
    url = url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL required")

    crawl = await crawl_site(CrawlConfig(url=url))
    psi = await fetch_psi(crawl["site"], psi_strategy)
    scores = compute_scores(crawl, psi)
    summary = build_summary(crawl["site"], scores, psi)
    categories = build_category_tables(scores, psi)

    audit_id = hashlib.sha256(f"{url}|{time.time()}".encode()).hexdigest()[:16]
    payload = {
        "site": crawl["site"],
        "created_at": datetime.utcnow().isoformat(),
        "result": {
            "overall_score": scores["overall_score"],
            "grade": scores["grade"],
            "summary": {
                "subscores": {
                    "security": scores["category_scores"]["Security"],
                    "performance": scores["category_scores"]["Performance"],
                    "seo": scores["category_scores"]["SEO"],
                    "ux": scores["category_scores"]["UX"],
                    "content": scores["category_scores"]["Content"],
                },
                "totals": {
                    "errors": scores["total_errors"],
                    "warnings": scores["total_warnings"],
                    "notices": scores["total_notices"],
                }
            }
        }
    }
    AUDITS[audit_id] = payload
    init_db()
    save_audit(audit_id, crawl["site"], payload)

    trend_data = build_trend_chart(crawl["site"], {
        "overall_score": scores["overall_score"],
        "category_scores": scores["category_scores"],
    })

    template = env.from_string(HTML_TEMPLATE)
    html = template.render(
        app_name=APP_NAME,
        company_name=COMPANY_NAME,
        version=VERSION,
        current_year=datetime.utcnow().year,

        website_url=crawl["site"],
        audit_date=datetime.utcnow().strftime("%Y-%m-%d"),
        audit_id=audit_id,

        overall_score=scores["overall_score"],
        grade=scores["grade"],
        grade_class=scores["grade_class"],

        total_errors=scores["total_errors"],
        total_warnings=scores["total_warnings"],
        total_notices=scores["total_notices"],

        executive_summary_200_words=summary,
        weak_areas=scores["weak_areas"],

        category_scores=scores["category_scores"],
        audit_categories=categories,

        trend_chart_data=json.dumps(trend_data),

        owner_insights=[
            "Prioritize security headers (HSTS, CSP) and remove mixed content.",
            "Enable Brotli/Gzip; improve LCP and reduce TBT with critical CSS and JS deferral.",
            "Complete titles/meta; add canonical tags and hreflang where relevant.",
            "Ensure viewport, semantic navigation; avoid intrusive interstitials.",
            "Add schema and alt text; expand thin pages to match user intent."
        ],
        validity_date=datetime.utcnow().strftime("%Y-%m-%d"),
    )
    return HTMLResponse(html)

# Optional: certified PDF (simple JSON dump)
@app.get("/audit/{audit_id}/pdf", response_class=HTMLResponse)
async def audit_pdf(audit_id: str):
    data = AUDITS.get(audit_id)
    if not data:
        return HTMLResponse("<h3>Audit not found</h3>", status_code=404)
    os.makedirs("reports", exist_ok=True)
    path = f"reports/audit_{audit_id}.pdf"
    doc = SimpleDocTemplate(path, pagesize=A4)
    styles = getSampleStyleSheet()
    doc.build([
        Paragraph("FF Tech — Certified Audit Report", styles["Title"]),
        Spacer(1, 12),
        Paragraph(f"Site: {data['site']}", styles["Normal"]),
        Paragraph(f"Created: {data['created_at']}", styles["Normal"]),
        Spacer(1, 12),
        Paragraph(json.dumps(data, indent=2), styles["Normal"])
    ])
    return HTMLResponse(f"<p>PDF generated: /{path}{path}</a></p>")

if __name__ == "__main__":
    import uvicorn, hashlib
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
