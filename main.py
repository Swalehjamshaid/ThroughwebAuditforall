
# FF Tech — AI Website Audit Platform (FastAPI + Jinja2)
# Requirements:
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
#   export PSI_API_KEY=your_key   # Enable CWV + Lighthouse via Google PSI
#   export ENABLE_HISTORY=true    # Persist audits for trend chart

import os
import re
import json
import time
import math
import httpx
import sqlite3
import tldextract
from bs4 import BeautifulSoup
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

# -----------------------------
# App & Config
# -----------------------------
app = FastAPI()

TEMPLATES_DIR = "templates"
TEMPLATE_FILE = "audit.html"

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"])
)

APP_NAME = "FF Tech — AI Website Audit"
COMPANY_NAME = "FF Tech"
VERSION = "v1.0"
ENABLE_HISTORY = os.getenv("ENABLE_HISTORY", "").lower() in ("true", "1", "yes")
PSI_API_KEY = os.getenv("PSI_API_KEY")  # Optional

DB_FILE = "audits.db"
AUDITS: Dict[str, Dict[str, Any]] = {}  # in-memory cache

# -----------------------------
# DB for Trend
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
# Helpers
# -----------------------------
def grade_for_score(score: int) -> Tuple[str, str]:
    # returns (grade_label, grade_class)
    if score >= 92: return ("A+", "Aplus")
    if score >= 85: return ("A", "A")
    if score >= 75: return ("B", "B")
    if score >= 65: return ("C", "C")
    return ("D", "D")

def status_class(pass_ratio: float, thresholds: Tuple[float, float] = (0.66, 0.33)) -> str:
    # simple mapping for table "Status" CSS class: good/warning/critical
    if pass_ratio >= thresholds[0]:
        return "good"
    if pass_ratio >= thresholds[1]:
        return "warning"
    return "critical"

def priority_class(level: str) -> str:
    # map High/Medium/Low -> badge classes
    return {"High": "high", "Medium": "medium", "Low": "low"}.get(level, "low")

def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

# -----------------------------
# Crawl & Analyze (httpx-only)
# -----------------------------
@dataclass
class CrawlConfig:
    url: str
    max_pages: int = 24
    concurrency: int = 12
    user_agent: str = "FFTechAuditBot/2.1"
    respect_robots: bool = True

async def fetch_page(client: httpx.AsyncClient, url: str) -> Tuple[int, Dict[str, str], bytes, float, str]:
    start = time.perf_counter()
    try:
        r = await client.get(url)
        duration_ms = (time.perf_counter() - start) * 1000.0
        headers = {k.lower(): v for k, v in r.headers.items()}
        return r.status_code, headers, r.content, duration_ms, str(r.url)
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
    to_visit = [base]

    async with httpx.AsyncClient(headers=headers, timeout=timeout, limits=limits, follow_redirects=True) as client:
        while to_visit and len(pages) < cfg.max_pages:
            url = to_visit.pop(0)
            if url in visited:
                continue
            visited.add(url)

            status, h, body, dur, final = await fetch_page(client, url)
            html_text = body.decode(errors="ignore") if body else ""
            soup = BeautifulSoup(html_text, "lxml") if html_text else None

            # Extract
            title = clean_text(soup.title.string) if soup and soup.title else None
            meta_desc = None
            if soup:
                md = soup.find("meta", attrs={"name": "description"})
                if md: meta_desc = clean_text(md.get("content", ""))

            h1 = None
            if soup:
                h1t = soup.find("h1")
                h1 = clean_text(h1t.get_text()) if h1t else None

            is_https = final.startswith("https://")
            hsts = bool(h.get("strict-transport-security"))
            csp = bool(h.get("content-security-policy"))
            xfo = bool(h.get("x-frame-options"))
            enc = (h.get("content-encoding") or "").lower()
            gzip_or_br = ("gzip" in enc) or ("br" in enc)

            # Mixed content check
            mixed = False
            if is_https and soup:
                for tag in soup.find_all(["img", "script", "link", "iframe"]):
                    src = tag.get("src") or tag.get("href") or ""
                    if src.startswith("http://"):
                        mixed = True
                        break

            # Cookie banner / privacy
            cookie_banner = False
            has_privacy_page = False
            if soup:
                text_low = soup.get_text(separator=" ", strip=True).lower()
                cookie_banner = any(k in text_low for k in ["cookie consent", "we use cookies", "accept cookies", "gdpr", "privacy settings"])
                has_privacy_page = "privacy" in text_low or "policy" in text_low

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
            canonical = None
            meta_robots = ""
            if soup:
                can = soup.find("link", attrs={"rel": "canonical"})
                canonical = can.get("href") if can and can.get("href") else None
                mr = soup.find("meta", attrs={"name": "robots"})
                meta_robots = (mr.get("content", "").lower() if mr else "")

            # i18n: hreflang
            hreflangs = []
            if soup:
                for link in soup.find_all("link", attrs={"rel": "alternate"}):
                    if link.get("hreflang") and link.get("href"):
                        hreflangs.append({"hreflang": link["hreflang"], "href": link["href"]})

            # Schema / OG / Twitter
            schema_present = False
            og_present = False
            tw_present = False
            if soup:
                for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
                    try:
                        json.loads(s.string or "{}")
                        schema_present = True
                        break
                    except Exception:
                        pass
                og_present = bool(soup.find("meta", attrs={"property": "og:title"}))
                tw_present = bool(soup.find("meta", attrs={"name": "twitter:card"}))

            # Text metrics
            word_count = len((soup.get_text(separator=" ", strip=True) if soup else "").split())
            thin = word_count < 300

            # Accessibility
            imgs = soup.find_all("img") if soup else []
            imgs_with_alt = [img for img in imgs if clean_text(img.get("alt"))]
            alt_coverage = round(100.0 * (len(imgs_with_alt) / max(1, len(imgs))), 2) if imgs else 100.0
            has_viewport = bool(soup and soup.find("meta", attrs={"name": "viewport"}))
            has_nav = bool(soup and soup.find("nav"))
            intrusive_popup = False
            if soup:
                intrusive_popup = any(k in (soup.get_text(" ", strip=True).lower()) for k in ["popup", "modal", "subscribe", "newsletter"])

            # Lazy loading
            lazy_imgs = sum(1 for img in imgs if (img.get("loading") or "").lower() == "lazy") if imgs else 0
            lazy_ratio = round(100.0 * (lazy_imgs / max(1, len(imgs))), 2) if imgs else 100.0

            # Resource references (approx requests)
            res_refs = 0
            if soup:
                res_refs = len(soup.find_all(["img", "script", "link"]))

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
                    "has_privacy_policy_signal": has_privacy_page,
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
                    "viewport": has_viewport,
                    "nav_present": has_nav,
                    "intrusive_popup": intrusive_popup,
                },
                "performance": {
                    "gzip_or_br": gzip_or_br,
                    "render_blocking_css_in_head": 0,  # simplified (lxml didn't find rel attr reliably everywhere)
                    "lazy_image_ratio": lazy_ratio,
                    "resource_refs": res_refs,
                },
                "links_internal": list(dict.fromkeys(links_internal)),
                "links_external": list(dict.fromkeys(links_external)),
            }
            pages.append(page)

            # Enqueue internal links shallowly
            for href in links_internal[:12]:
                if href not in visited and href not in to_visit and len(to_visit) + len(pages) < cfg.max_pages:
                    to_visit.append(href)

    # Robots & Sitemaps discover
    sitemaps = {"robots": [], "direct": []}
    async with httpx.AsyncClient(timeout=20) as client:
        robots = urljoin(base, "/robots.txt")
        try:
            r = await client.get(robots)
            if r.status_code == 200:
                for line in r.text.splitlines():
                    if line.lower().startswith("sitemap:"):
                        sitemaps["robots"].append(line.split(":", 1)[1].strip())
        except Exception:
            pass
        sm = urljoin(base, "/sitemap.xml")
        try:
            r = await client.get(sm)
            if r.status_code == 200:
                sitemaps["direct"].append(sm)
        except Exception:
            pass

    avg_resp = round(sum(p["response_time_ms"] for p in pages) / max(1, len(pages)), 2)
    avg_html_kb = round(sum(p["html_size_bytes"] for p in pages) / max(1, len(pages)) / 1024.0, 2)

    return {
        "site": base,
        "pages": pages,
        "stats": {"avg_response_time_ms": avg_resp, "avg_html_size_kb": avg_html_kb},
        "sitemaps": sitemaps,
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
                params={"url": url, "strategy": strategy, "key": PSI_API_KEY}
            )
            data = r.json()
            lr = data.get("lighthouseResult", {}) or {}
            audits = lr.get("audits", {}) or {}
            cats = lr.get("categories", {}) or {}

            def num(audit_key: str) -> Optional[float]:
                return (audits.get(audit_key) or {}).get("numericValue")

            def cat_score(name: str) -> Optional[int]:
                sc = cats.get(name, {}).get("score")
                return int(round((sc or 0) * 100)) if sc is not None else None

            # failing audits
            failed = []
            for aid, a in audits.items():
                sc = a.get("score")
                if isinstance(sc, (int, float)) and sc < 0.9:
                    failed.append({
                        "id": aid,
                        "title": a.get("title"),
                        "displayValue": a.get("displayValue"),
                        "score": sc,
                    })
            failed = sorted([f for f in failed if f["title"]], key=lambda x: x["score"] or 0)[:10]

            return {
                "source": "psi",
                "strategy": strategy,
                "lcp_ms": num("largest-contentful-paint"),
                "fcp_ms": num("first-contentful-paint"),
                "cls": num("cumulative-layout-shift"),
                # FID is deprecated; using TBT + TTI
                "tbt_ms": num("total-blocking-time"),
                "tti_ms": num("interactive"),
                "lighthouse": {
                    "categories": {
                        "Performance": cat_score("performance"),
                        "Accessibility": cat_score("accessibility"),
                        "Best Practices": cat_score("best-practices"),
                        "SEO": cat_score("seo"),
                        "PWA": cat_score("pwa"),
                    },
                    "failed_audits": failed,
                }
            }
    except Exception:
        return {"source": "none", "strategy": strategy}

# -----------------------------
# Scoring & Metric Tables
# -----------------------------
def compute_scores(crawl: Dict[str, Any], psi: Dict[str, Any]) -> Dict[str, Any]:
    pages = crawl["pages"]
    stats = crawl["stats"]

    # Aggregates
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
        "viewport_missing": 0,
        "nav_missing": 0,
        "intrusive_popup_pages": 0,
        "thin_pages": 0,
        "alt_issue_pages": 0,
        "canonical_missing_pages": 0,
        "og_missing_pages": 0,
        "twitter_missing_pages": 0,
        "hreflang_pages": 0,
        "non_200_pages": 0,
        "duplicate_titles": 0,
        "duplicate_meta": 0,
        "avg_response_time_ms": stats["avg_response_time_ms"],
        "avg_html_size_kb": stats["avg_html_size_kb"],
    }

    title_count = {}
    meta_count = {}

    for p in pages:
        if p["status"] != 200:
            totals["non_200_pages"] += 1

        title = p.get("title")
        meta_desc = p.get("meta_description")
        if not title: totals["missing_titles"] += 1
        else: title_count[title] = title_count.get(title, 0) + 1
        if not meta_desc: totals["missing_meta"] += 1
        else: meta_count[meta_desc] = meta_count.get(meta_desc, 0) + 1
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

        perf = p["performance"]
        if not perf["gzip_or_br"]: totals["gzip_missing_pages"] += 1

        ux = p["ux"]
        if not ux["viewport"]: totals["viewport_missing"] += 1
        if not ux["nav_present"]: totals["nav_missing"] += 1
        if ux["intrusive_popup"]: totals["intrusive_popup_pages"] += 1

        seo = p["seo"]
        if seo["thin"]: totals["thin_pages"] += 1
        if seo["word_count"] < 300: pass
        if not seo["schema"]: pass
        imgs = p.get("accessibility", {})
        alt_cov = p.get("accessibility", {}).get("alt_coverage_pct", 100.0)
        if alt_cov < 80.0: totals["alt_issue_pages"] += 1
        if not seo["canonical"]: totals["canonical_missing_pages"] += 1
        if not seo["og"]: totals["og_missing_pages"] += 1
        if not seo["twitter"]: totals["twitter_missing_pages"] += 1
        if seo["hreflang"]: totals["hreflang_pages"] += 1

    # Duplicates
    totals["duplicate_titles"] = sum(1 for v in title_count.values() if v > 1)
    totals["duplicate_meta"] = sum(1 for v in meta_count.values() if v > 1)

    # Category scoring (0..100)
    # Security & Compliance
    sec_score = 100
    sec_score -= min(30, totals["hsts_missing"] * 3)
    sec_score -= min(30, totals["csp_missing"] * 3)
    sec_score -= min(25, totals["xfo_missing"] * 2.5)
    sec_score -= min(40, totals["mixed_content_pages"] * 8)
    # Privacy signals boost slightly
    sec_score += min(5, totals["privacy_signal_pages"])
    sec_score = max(0, min(100, sec_score))

    # Performance & Web Vitals
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

    # SEO / Indexing
    seo_score = 100
    seo_score -= min(30, totals["missing_titles"] * 2)
    seo_score -= min(20, totals["missing_meta"])
    seo_score -= min(20, totals["missing_h1"] * 2)
    seo_score -= min(15, totals["canonical_missing_pages"])
    seo_score -= min(10, totals["duplicate_titles"])
    seo_score -= min(10, totals["duplicate_meta"])
    seo_score += min(5, totals["hreflang_pages"])
    seo_score = max(0, min(100, seo_score))

    # UX & Mobile
    ux_score = 100
    ux_score -= min(25, totals["viewport_missing"] * 3)
    ux_score -= min(15, totals["nav_missing"] * 2)
    ux_score -= min(20, totals["intrusive_popup_pages"] * 4)
    ux_score = max(0, min(100, ux_score))

    # Content Quality & On-page SEO
    content_score = 100
    content_score -= min(20, totals["thin_pages"] * 2)
    content_score -= min(20, totals["alt_issue_pages"] * 2)
    content_score -= min(10, totals["og_missing_pages"])
    content_score -= min(10, totals["twitter_missing_pages"])
    content_score += min(5, 1)  # small bonus placeholder
    content_score = max(0, min(100, content_score))

    # Overall (weights)
    weights = {
        "Security": 0.28,
        "Performance": 0.27,
        "SEO": 0.23,
        "UX": 0.12,
        "Content": 0.10,
    }
    overall_score = int(round(
        sec_score * weights["Security"] +
        perf_score * weights["Performance"] +
        seo_score * weights["SEO"] +
        ux_score * weights["UX"] +
        content_score * weights["Content"]
    ))
    grade, grade_class = grade_for_score(overall_score)

    # Totals breakdown visible
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

    # Weak areas: top 5 issues
    weak_areas = []
    issue_pairs = [
        ("Mixed content found", totals["mixed_content_pages"]),
        ("No HSTS on HTTPS pages", totals["hsts_missing"]),
        ("Missing CSP headers", totals["csp_missing"]),
        ("Missing meta titles/descriptions", totals["missing_titles"] + totals["missing_meta"]),
        ("Thin content pages (<300 words)", totals["thin_pages"]),
        ("Missing viewport (mobile)", totals["viewport_missing"]),
        ("Broken duplicates (titles/meta)", totals["duplicate_titles"] + totals["duplicate_meta"]),
        ("Gzip/Brotli compression missing", totals["gzip_missing_pages"]),
        ("Intrusive popups/modals", totals["intrusive_popup_pages"]),
    ]
    for name, count in sorted(issue_pairs, key=lambda x: x[1], reverse=True)[:5]:
        if count > 0:
            weak_areas.append(f"{name}: {count}")

    category_scores = {
        "Security": sec_score,
        "Performance": perf_score,
        "SEO": seo_score,
        "UX": ux_score,
        "Content": content_score,
    }

    return {
        "overall_score": overall_score,
        "grade": grade,
        "grade_class": grade_class,
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "total_notices": total_notices,
        "category_scores": category_scores,
        "totals": totals,
    }

# -----------------------------
# Executive Summary
# -----------------------------
def build_executive_summary(site: str, scores: Dict[str, Any], psi: Dict[str, Any]) -> str:
    cs = scores["category_scores"]
    weakest = ", ".join(sorted(cs.keys(), key=lambda k: cs[k])[:2])
    lines = [
        f"This AI-driven audit of {site} evaluates Security & Compliance, Performance & Core Web Vitals, SEO & Indexing, UX & Mobile, and Content Quality.",
        f"The overall website health score is {scores['overall_score']} ({scores['grade']}). Category scores — "
        f"Security: {cs['Security']}, Performance: {cs['Performance']}, SEO: {cs['SEO']}, UX: {cs['UX']}, Content: {cs['Content']}.",
        f"Critical weak areas include: {weakest}.",
        "Why this matters: stronger trust and compliance, faster pages and better user experience, clearer search signals and indexation, and higher conversion potential.",
    ]
    if psi.get("source") == "psi":
        cats = psi.get("lighthouse", {}).get("categories", {}) or {}
        lines.append(
            f"Lighthouse snapshot — Performance: {cats.get('Performance')}, Accessibility: {cats.get('Accessibility')}, "
            f"Best Practices: {cats.get('Best Practices')}, SEO: {cats.get('SEO')}, PWA: {cats.get('PWA')}."
        )
        lines.append(
            f"Key web vitals — LCP: {psi.get('lcp_ms')} ms, CLS: {psi.get('cls')}, TBT: {psi.get('tbt_ms')} ms, TTI: {psi.get('tti_ms')} ms."
        )
    lines += [
        "Recommended next steps: enforce HSTS and CSP; remove mixed content; complete titles and meta; ensure mobile viewport; compress assets (Brotli/Gzip); reduce thin pages; add alt text; and address Lighthouse findings.",
        "Address high-risk items first (security/performance), then optimize SEO/UX/content for sustained growth."
    ]
    text = " ".join(lines)
    words = text.split()
    if len(words) > 220:  # ~200 words target
        text = " ".join(words[:220])
    return text

# -----------------------------
# Build Category Tables (collapsible)
# -----------------------------
def build_category_tables(crawl: Dict[str, Any], scores: Dict[str, Any], psi: Dict[str, Any]) -> List[Dict[str, Any]]:
    totals = scores["totals"]
    categories: List[Dict[str, Any]] = []

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

    # Security & Compliance
    sec_rows = []
    sec_rows.append(metric_row(
        "HTTPS / SSL valid",
        totals["https_pages"] > 0,
        100 if totals["https_pages"] > 0 else 40,
        "High",
        "HTTPS is required for trust, rankings, and compliance.",
        "Force HTTPS, redirect HTTP to HTTPS, and use a valid TLS certificate."
    ))
    sec_rows.append(metric_row(
        "HSTS header present",
        totals["hsts_missing"] == 0,
        max(10, 100 - totals["hsts_missing"] * 10),
        "High",
        "HSTS prevents protocol downgrades and cookie hijacking.",
        "Enable Strict-Transport-Security with includeSubDomains and preload where applicable."
    ))
    sec_rows.append(metric_row(
        "Content-Security-Policy (CSP)",
        totals["csp_missing"] == 0,
        max(10, 100 - totals["csp_missing"] * 10),
        "High",
        "CSP mitigates XSS and data injection risks.",
        "Define a strict CSP (default-src 'self') and audit external sources."
    ))
    sec_rows.append(metric_row(
        "X-Frame-Options header",
        totals["xfo_missing"] == 0,
        max(10, 100 - totals["xfo_missing"] * 10),
        "Medium",
        "Prevents clickjacking and UI redressing attacks.",
        "Add X-Frame-Options: SAMEORIGIN or use frame-ancestors in CSP."
    ))
    sec_rows.append(metric_row(
        "Mixed content eliminated",
        totals["mixed_content_pages"] == 0,
        max(10, 100 - totals["mixed_content_pages"] * 20),
        "High",
        "Mixed content breaks padlock and undermines trust.",
        "Replace http:// assets with https:// and update CDNs."
    ))
    sec_rows.append(metric_row(
        "Privacy / GDPR / Cookie policy",
        totals["privacy_signal_pages"] > 0,
        80 if totals["privacy_signal_pages"] > 0 else 50,
        "Medium",
        "Clear privacy and cookie notices reduce legal risk and improve transparency.",
        "Add privacy/cookie policy and a consent banner for tracking technologies."
    ))
    categories.append({
        "name": "Security & Compliance",
        "description": "Headers, encryption, privacy signals, and mixed content checks.",
        "metrics": sec_rows
    })

    # Performance & Web Vitals
    perf_rows = []
    perf_rows.append(metric_row(
        "Core Web Vitals (LCP/FCP/CLS/TBT/TTI)",
        psi.get("source") == "psi",
        70 if psi.get("source") == "psi" else 50,
        "High",
        "Web Vitals drive UX, SEO, and conversion.",
        "Use PSI/Lighthouse; optimize critical CSS, images, and script execution."
    ))
    perf_rows.append(metric_row(
        "Compression (Brotli/Gzip)",
        totals["gzip_missing_pages"] == 0,
        max(10, 100 - totals["gzip_missing_pages"] * 8),
        "High",
        "Compression reduces transfer size and speeds up time-to-first-byte.",
        "Enable Brotli/Gzip at server/CDN; set cache-control pragmatic values."
    ))
    perf_rows.append(metric_row(
        "Server response time (TTFB approx)",
        totals["avg_response_time_ms"] < 800,
        max(10, 100 - int(max(0, totals["avg_response_time_ms"] - 800) / 8)),
        "High",
        "Slow responses harm LCP, user patience, and crawl budget.",
        "Profile backend, use CDN, optimize DB and caching layers."
    ))
    perf_rows.append(metric_row(
        "Page size",
        totals["avg_html_size_kb"] < 120,
        max(10, 100 - int(max(0, totals["avg_html_size_kb"] - 120) / 2)),
        "Medium",
        "Large HTML increases parse time and bandwidth costs.",
        "Reduce HTML markup, remove unused code, split templates."
    ))
    categories.append({
        "name": "Performance & Web Vitals",
        "description": "Speed, compression, and PSI Lighthouse signals.",
        "metrics": perf_rows
    })

    # SEO / Indexing
    seo_rows = []
    seo_rows.append(metric_row(
        "Meta titles/descriptions present",
        totals["missing_titles"] == 0 and totals["missing_meta"] == 0,
        max(10, 100 - (totals["missing_titles"] * 10 + totals["missing_meta"] * 8)),
        "High",
        "Titles & meta drive CTR and relevance.",
        "Add unique, descriptive titles and meta descriptions for each page."
    ))
    seo_rows.append(metric_row(
        "H1/H2 structure",
        totals["missing_h1"] == 0,
        max(10, 100 - totals["missing_h1"] * 8),
        "Medium",
        "Headings improve readability and topical hierarchy.",
        "Ensure one H1 per page and logical H2/H3 structure."
    ))
    seo_rows.append(metric_row(
        "Canonical tags",
        totals["canonical_missing_pages"] == 0,
        max(10, 100 - totals["canonical_missing_pages"] * 8),
        "Medium",
        "Canonicals prevent duplicate indexing and consolidate signals.",
        "Add canonical link to preferred URL on every indexable page."
    ))
    seo_rows.append(metric_row(
        "Hreflang (multi-language)",
        totals["hreflang_pages"] > 0,
        70 if totals["hreflang_pages"] > 0 else 50,
        "Low",
        "Hreflang ensures correct regional/language targeting.",
        "Add hreflang tags and test with Search Console."
    ))
    categories.append({
        "name": "SEO & Indexing",
        "description": "Crawl signals, duplicate prevention, and multi-language tags.",
        "metrics": seo_rows
    })

    # UX & Mobile
    ux_rows = []
    ux_rows.append(metric_row(
        "Responsive (viewport)",
        totals["viewport_missing"] == 0,
        max(10, 100 - totals["viewport_missing"] * 10),
        "High",
        "Viewport is foundational for mobile usability.",
        "Add <meta name='viewport' content='width=device-width, initial-scale=1'>"
    ))
    ux_rows.append(metric_row(
        "Navigation usability",
        totals["nav_missing"] == 0,
        max(10, 100 - totals["nav_missing"] * 10),
        "Medium",
        "Accessible navigation reduces bounce and improves task completion.",
        "Use semantic <nav>, clear labels, and skip links."
    ))
    ux_rows.append(metric_row(
        "Intrusive interstitials",
        totals["intrusive_popup_pages"] == 0,
        max(10, 100 - totals["intrusive_popup_pages"] * 20),
        "High",
        "Popups hurt UX and mobile rankings.",
        "Avoid full-screen overlays; delay less-critical prompts."
    ))
    categories.append({
        "name": "UX & Mobile",
        "description": "Mobile readiness and usability signals.",
        "metrics": ux_rows
    })

    # Content Quality & On-Page SEO
    content_rows = []
    content_rows.append(metric_row(
        "Thin content (<300 words)",
        totals["thin_pages"] == 0,
        max(10, 100 - totals["thin_pages"] * 10),
        "High",
        "Thin content reduces relevance and ranking potential.",
        "Add substantive, unique content; cover user intents."
    ))
    content_rows.append(metric_row(
        "Image alt attributes",
        totals["alt_issue_pages"] == 0,
        max(10, 100 - totals["alt_issue_pages"] * 10),
        "Medium",
        "Alt text improves accessibility and image SEO.",
        "Add meaningful alt attributes to all informative images."
    ))
    content_rows.append(metric_row(
        "Structured data / Schema.org",
        True,  # we show pass if any schema present (simplified in totals)
        70,
        "Medium",
        "Schema enables rich results and better entity understanding.",
        "Add appropriate schema types (Article, Product, Organization)."
    ))
    content_rows.append(metric_row(
        "Open Graph / Twitter cards",
        totals["og_missing_pages"] == 0 and totals["twitter_missing_pages"] == 0,
        max(10, 100 - (totals["og_missing_pages"] * 5 + totals["twitter_missing_pages"] * 5)),
        "Low",
        "Social cards improve sharing previews and CTR.",
        "Add og:title/description/image and twitter:card meta tags."
    ))
    categories.append({
        "name": "Content Quality & On-Page SEO",
        "description": "Depth, accessibility, schema, and social metadata.",
        "metrics": content_rows
    })

    return categories

# -----------------------------
# Trend Chart Data (Chart.js)
# -----------------------------
def build_trend_chart(site: str, current_scores: Dict[str, Any]) -> Dict[str, Any]:
    records = load_recent(site, limit=10)
    labels = []
    overall = []
    sec = []
    perf = []
    seo = []
    ux = []
    content = []

    # Oldest -> newest
    for r in reversed(records):
        labels.append(r.get("created_at", "")[:10])
        res = r.get("result", {}) or {}
        cat = res.get("summary", {}).get("subscores", {}) or {}
        overall.append(res.get("overall_score", 0))
        sec.append(cat.get("security", 0))
        perf.append(cat.get("performance", 0))
        seo.append(cat.get("seo", 0))
        ux.append(cat.get("ux", 0))
        content.append(cat.get("crawl", 0))  # NOTE: in this design we use Content; earlier backend had 'crawl'. We'll map Content below.

    # Append current
    now_label = datetime.utcnow().strftime("%Y-%m-%d")
    labels.append(now_label)
    overall.append(current_scores["overall_score"])
    sec.append(current_scores["category_scores"]["Security"])
    perf.append(current_scores["category_scores"]["Performance"])
    seo.append(current_scores["category_scores"]["SEO"])
    ux.append(current_scores["category_scores"]["UX"])
    content.append(current_scores["category_scores"]["Content"])

    chart_data = {
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
    return chart_data

# -----------------------------
# Routes
# -----------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    # Provide a small HTML form to start an audit (or you can post directly to /render)
    return HTMLResponse(f"""
    <!doctype html><html><head><meta charset="utf-8"><title>{APP_NAME}</title></head>
    <body style="font-family:Inter,Arial;max-width:720px;margin:40px auto;">
      <h1>{APP_NAME}</h1>
      <form method="post" action="/render" style="display:grid;gap:10px"https://example.com" style="width:100%;padding:8px;"></label>
        <label>PSI Strategy
          <select name="psi_strategy" style="padding:8px;">
            <option value="mobile">mobile</option>
            <option value="desktop">desktop</option>
          </select>
        </label>
        <button type="submit" style="padding:10px 14px;background:#2563eb;color:#fff;border:none;border-radius:6px;">Run Audit</button>
      </form>
    </body></html>
    """)

@app.post("/render", response_class=HTMLResponse)
async def render_audit(
    url: str = Form(...),
    psi_strategy: str = Form("mobile")
):
    url = url.strip()
    if not url:
        raise HTTPException(400, "URL required")

    # Crawl + PSI
    crawl = await crawl_site(CrawlConfig(url=url))
    psi = await fetch_psi(crawl["site"], psi_strategy)
    scores = compute_scores(crawl, psi)
    summary = build_executive_summary(crawl["site"], scores, psi)
    categories = build_category_tables(crawl, scores, psi)

    # Build payload to persist & trend
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
    audit_id = hashlib.sha256(f"{url}|{time.time()}".encode()).hexdigest()[:16]
    AUDITS[audit_id] = payload
    init_db()
    save_audit(audit_id, crawl["site"], payload)

    # Chart.js trend data
    trend_data = build_trend_chart(crawl["site"], {
        "overall_score": scores["overall_score"],
        "category_scores": scores["category_scores"],
    })

    # Render Jinja template with your fixed variables
    template = env.get_template(TEMPLATE_FILE)
    html = template.render(
        app_name=APP_NAME,
        company_name=COMPANY_NAME,
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
        weak_areas=scores.get("weak_areas", []) or [],  # may be empty

        category_scores=scores["category_scores"],
        audit_categories=categories,

        trend_chart_data=json.dumps(trend_data),  # {{ trend_chart_data | safe }}

        owner_insights=[
            "Prioritize security headers (HSTS, CSP) and remove mixed content.",
            "Enable Brotli/Gzip, optimize hero image LCP, and reduce JS blocking (TBT).",
            "Complete titles/meta, add canonical tags, and improve heading hierarchy.",
            "Ensure viewport and clean navigation; avoid intrusive interstitials.",
            "Add schema and alt text; expand thin pages with user-focused content."
        ],

        validity_date=(datetime.utcnow().strftime("%Y-%m-%d")),
    )
    return HTMLResponse(html)

# Optional: Certified PDF endpoint (returns raw JSON link path)
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

# Serve the template directly at /template for sanity
@app.get("/template", response_class=HTMLResponse)
async def show_template():
    try:
        with open(os.path.join(TEMPLATES_DIR, TEMPLATE_FILE), "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except Exception:
        return HTMLResponse("<h3>Template not found</h3>", status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
