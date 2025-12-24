
# FF Tech - Enterprise AI Website Audit (Single-File Backend, Lighthouse-enabled, httpx-only)
# Run locally:
#   python -m venv .venv && . .venv/bin/activate
#   pip install -r requirements.txt
#   uvicorn main:app --reload
#
# Optional env:
#   export PSI_API_KEY=xxxxxx         # enables Lighthouse + Core Web Vitals via Google PSI
#   export ENABLE_HISTORY=true        # persists audits for the trend endpoint (SQLite)

import os
import time
import json
import sqlite3
import hashlib
import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Any, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import httpx
import tldextract
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

app = FastAPI()

# In-memory store
AUDITS: Dict[str, Dict[str, Any]] = {}

# Environment flags
DB_FILE = "audits.db"
ENABLE_HISTORY = os.environ.get("ENABLE_HISTORY", "").lower() in ("1", "true", "yes")
PSI_API_KEY = os.environ.get("PSI_API_KEY")  # optional

# -------------------------------------------------------------------
# Persistence (SQLite) for trend endpoint
# -------------------------------------------------------------------
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

def load_recent_audits(site: str, limit: int = 10) -> List[dict]:
    if not ENABLE_HISTORY:
        return []
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute(
        "SELECT payload_json FROM audits WHERE site=? ORDER BY created_at DESC LIMIT ?",
        (site, limit)
    ).fetchall()
    conn.close()
    return [json.loads(r[0]) for r in rows]

# -------------------------------------------------------------------
# Config dataclass
# -------------------------------------------------------------------
@dataclass
class AuditConfig:
    url: str
    deep: bool = True
    max_pages: int = 24
    respect_robots: bool = True
    concurrency: int = 24
    user_agent: str = "FFTechAuditBot/2.1"
    psi_strategy: str = "mobile"  # or "desktop"
    link_check_sample_per_page: int = 25
    sitemap_max_depth: int = 4
    sitemap_max_urls: int = 50000

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

# -------------------------------------------------------------------
# Audit Engine (httpx-only)
# -------------------------------------------------------------------
class AuditEngine:
    def __init__(self, cfg: AuditConfig):
        self.cfg = cfg
        parsed = urlparse(cfg.url)
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc or parsed.path
        self.base_url = f"{scheme}://{netloc}"
        self.root_domain = tldextract.extract(netloc).registered_domain
        self.client: Optional[httpx.AsyncClient] = None
        self.robots_rules: Optional[Dict[str, Any]] = None

    async def run(self) -> Dict[str, Any]:
        headers = {"User-Agent": self.cfg.user_agent}
        limits = httpx.Limits(max_connections=self.cfg.concurrency, max_keepalive_connections=self.cfg.concurrency)
        timeout = httpx.Timeout(30.0)
        async with httpx.AsyncClient(headers=headers, timeout=timeout, limits=limits, follow_redirects=True) as client:
            self.client = client
            await self._load_robots()
            pages, crawl_stats = await self._crawl()
            sitemaps = await self._discover_sitemaps()
            cwv_lh = await self._core_web_vitals(self.base_url, self.cfg.psi_strategy)
            return {
                "site": self.base_url,
                "config": self.cfg.to_dict(),
                "pages": pages,
                "crawl_stats": crawl_stats,
                "sitemaps": sitemaps,
                "cwv": cwv_lh,  # Core Web Vitals & Lighthouse (if PSI enabled)
            }

    async def _load_robots(self):
        if not self.cfg.respect_robots:
            return
        robots_url = urljoin(self.base_url, "/robots.txt")
        try:
            r = await self.client.get(robots_url)
            if r.status_code == 200:
                disallow = []
                for line in r.text.splitlines():
                    line = line.strip()
                    if line.lower().startswith("disallow:"):
                        path = line.split(":", 1)[1].strip()
                        disallow.append(path)
                self.robots_rules = {"disallow": disallow}
        except Exception:
            self.robots_rules = None

    def _robots_allowed(self, path: str) -> bool:
        if not self.cfg.respect_robots or not self.robots_rules:
            return True
        for rule in self.robots_rules.get("disallow", []):
            if rule and path.startswith(rule):
                return False
        return True

    async def _fetch(self, url: str) -> Tuple[int, Dict[str, str], bytes, float, str]:
        start = time.perf_counter()
        try:
            r = await self.client.get(url)
            status = r.status_code
            headers = {k.lower(): v for k, v in r.headers.items()}
            body = r.content
            duration = (time.perf_counter() - start) * 1000.0
            final_url = str(r.url)
            return status, headers, body, duration, final_url
        except Exception:
            return 0, {}, b"", (time.perf_counter() - start) * 1000.0, url

    async def _crawl(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        visited: Set[str] = set()
        q: asyncio.Queue = asyncio.Queue()
        await q.put(self.base_url)
        pages: List[Dict[str, Any]] = []
        sem = asyncio.Semaphore(self.cfg.concurrency)

        async def worker():
            while True:
                try:
                    url = await asyncio.wait_for(q.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    return
                if url in visited or len(pages) >= self.cfg.max_pages:
                    q.task_done()
                    continue
                visited.add(url)
                path = urlparse(url).path
                if not self._robots_allowed(path):
                    pages.append({"url": url, "status": 999, "error": "Blocked by robots.txt"})
                    q.task_done()
                    continue
                async with sem:
                    status, headers, body, duration, final_url = await self._fetch(url)
                page = await self._analyze_page(url, final_url, status, headers, body, duration)
                pages.append(page)
                q.task_done()
                if self.cfg.deep and status == 200 and page.get("links_internal"):
                    for link in page["links_internal"]:
                        if link not in visited and tldextract.extract(urlparse(link).netloc).registered_domain == self.root_domain:
                            if len(pages) + q.qsize() < self.cfg.max_pages:
                                await q.put(link)

        workers = [asyncio.create_task(worker()) for _ in range(max(2, self.cfg.concurrency // 2))]
        await asyncio.gather(*workers)

        avg_resp = sum(p.get("response_time_ms", 0.0) for p in pages) / max(1, len(pages))
        avg_html_kb = sum(p.get("html_size_bytes", 0) for p in pages) / max(1, len(pages)) / 1024.0
        return pages, {
            "total_pages": len(pages),
            "avg_response_time_ms": round(avg_resp, 2),
            "avg_html_size_kb": round(avg_html_kb, 2),
        }

    async def _analyze_page(
        self,
        requested_url: str,
        final_url: str,
        status: int,
        headers: Dict[str, str],
        body: bytes,
        duration_ms: float
    ) -> Dict[str, Any]:
        html_text = body.decode(errors="ignore") if body else ""
        soup = BeautifulSoup(html_text, "lxml") if html_text else None
        is_https = final_url.startswith("https://")

        # Title, meta, H1
        title = (soup.title.string.strip() if soup and soup.title and soup.title.string else None)
        meta_desc = None
        if soup:
            md = soup.find("meta", attrs={"name": "description"})
            if md:
                meta_desc = md.get("content", "").strip()
        h1 = None
        if soup:
            h1_tag = soup.find("h1")
            h1 = h1_tag.get_text(strip=True) if h1_tag else None

        # Security headers
        hsts = bool(headers.get("strict-transport-security"))
        csp = bool(headers.get("content-security-policy"))

        # Mixed content
        mixed = False
        if is_https and soup:
            for tag in soup.find_all(["img", "script", "link", "iframe"]):
                src = tag.get("src") or tag.get("href") or ""
                if src.startswith("http://"):
                    mixed = True
                    break

        # Cookie banner heuristic
        cookie_banner = False
        if soup:
            text = soup.get_text(separator=" ", strip=True).lower()
            cookie_banner = any(k in text for k in ["cookie consent", "we use cookies", "accept cookies", "gdpr", "privacy settings"])

        # Compression check (gzip/brotli)
        enc = (headers.get("content-encoding") or "").lower()
        gzip_missing = ("gzip" not in enc) and ("br" not in enc)

        # Render-blocking CSS count in <head>
        rb_css = 0
        if soup:
            head = soup.find("head")
            if head:
                rb_css = len([l for l in head.find_all("link") if (l.get("rel") or []) and "stylesheet" in l.get("rel")])

        # Links
        links_internal: List[str] = []
        links_external: List[str] = []

        def norm(u: str) -> Optional[str]:
            if not u:
                return None
            u = u.strip()
            if u.startswith("#") or u.startswith("javascript:"):
                return None
            return urljoin(final_url, u)

        if soup:
            for a in soup.find_all("a"):
                href = norm(a.get("href"))
                if not href:
                    continue
                if tldextract.extract(urlparse(href).netloc).registered_domain == self.root_domain:
                    links_internal.append(href)
                else:
                    links_external.append(href)

        # Canonical / robots meta
        canonical_issue = False
        meta_robots = ""
        if soup:
            can = soup.find("link", attrs={"rel": "canonical"})
            if not can or not can.get("href"):
                canonical_issue = True
            mr = soup.find("meta", attrs={"name": "robots"})
            meta_robots = (mr.get("content", "").lower() if mr else "")

        # Text-to-HTML ratio
        text_len = len(soup.get_text(separator=" ", strip=True)) if soup else 0
        ratio_text_html = (text_len / max(1, len(html_text))) if html_text else 0.0

        # Mobile viewport
        viewport = bool(soup.find("meta", attrs={"name": "viewport"})) if soup else False

        # Accessibility heuristics
        img_tags = soup.find_all("img") if soup else []
        img_with_alt = [img for img in img_tags if (img.get("alt") or "").strip()]
        alt_coverage_pct = round(100.0 * (len(img_with_alt) / max(1, len(img_tags))), 2) if img_tags else 100.0
        heading_count = sum(len(soup.find_all(h)) for h in ["h1", "h2", "h3", "h4", "h5", "h6"]) if soup else 0
        has_landmarks = any(soup.find(tag) for tag in ["nav", "main", "header", "footer", "aside"]) if soup else False
        aria_count = sum(1 for tag in soup.find_all(True) if any(a.startswith("aria-") for a in tag.attrs)) if soup else 0

        # International SEO signals
        hreflangs = []
        lang_attr_issues = False
        if soup:
            for link in soup.find_all("link", attrs={"rel": "alternate"}):
                if link.get("hreflang") and link.get("href"):
                    hreflangs.append({"hreflang": link["hreflang"], "href": link["href"]})
            html_tag = soup.find("html")
            if html_tag:
                lang_val = (html_tag.get("lang") or "").strip()
                # basic sanity: ISO codes are typically 2-5 chars (e.g., en, en-US)
                if lang_val and not (2 <= len(lang_val) <= 5):
                    lang_attr_issues = True

        # Schema presence
        schema_present = False
        if soup:
            for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
                try:
                    json.loads(script.string or "{}")
                    schema_present = True
                    break
                except Exception:
                    pass

        return {
            "requested_url": requested_url,
            "url": final_url,
            "status": status,
            "response_time_ms": round(duration_ms, 2),
            "html_size_bytes": len(body or b""),
            "title": title,
            "meta_description": meta_desc,
            "h1": h1,
            "has_viewport": viewport,
            "security": {
                "is_https": is_https,
                "hsts": hsts,
                "csp": csp,
                "mixed_content": mixed,
            },
            "cookie_banner": cookie_banner,
            "headers": headers,
            "links_internal": list(dict.fromkeys(links_internal)),
            "links_external": list(dict.fromkeys(links_external)),
            "seo": {
                "canonical_issue": canonical_issue,
                "meta_robots": meta_robots,
                "text_to_html_ratio": round(ratio_text_html, 4),
                "schema_present": schema_present,
            },
            "performance": {
                "gzip_missing": gzip_missing,
                "render_blocking_css_in_head": rb_css,
            },
            "accessibility": {
                "alt_coverage_pct": alt_coverage_pct,
                "heading_count": heading_count,
                "has_landmarks": has_landmarks,
                "aria_count": aria_count,
            },
            "i18n": {
                "hreflang": hreflangs,
                "lang_attr_issues": lang_attr_issues,
            },
        }

    async def _discover_sitemaps(self) -> Dict[str, Any]:
        sitemaps = {"robots": [], "direct": []}
        # robots.txt sitemaps
        robots_url = urljoin(self.base_url, "/robots.txt")
        try:
            r = await self.client.get(robots_url)
            if r.status_code == 200:
                for line in r.text.splitlines():
                    if line.lower().startswith("sitemap:"):
                        sitemaps["robots"].append(line.split(":", 1)[1].strip())
        except Exception:
            pass
        # direct /sitemap.xml
        sm_url = urljoin(self.base_url, "/sitemap.xml")
        try:
            r = await self.client.get(sm_url)
            if r.status_code == 200:
                sitemaps["direct"].append(sm_url)
        except Exception:
            pass
        return sitemaps

    async def _core_web_vitals(self, url: str, strategy: str = "mobile") -> Dict[str, Any]:
        # PSI first (provides Lighthouse and CWV)
        if PSI_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    r = await client.get(
                        "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
                        params={"url": url, "strategy": strategy, "key": PSI_API_KEY},
                    )
                    data = r.json()
                    lh = data.get("lighthouseResult", {}) or {}
                    audits = lh.get("audits", {}) or {}
                    cats = lh.get("categories", {}) or {}
                    metrics = data.get("loadingExperience", {}).get("metrics", {}) or {}

                    def audit_num(key: str) -> Optional[float]:
                        node = audits.get(key) or {}
                        return node.get("numericValue")

                    def cat_score(name: str) -> Optional[int]:
                        sc = cats.get(name, {}).get("score")
                        return int(round(sc * 100)) if sc is not None else None

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
                        "lcp_ms": audit_num("largest-contentful-paint"),
                        "cls": audit_num("cumulative-layout-shift"),
                        "tbt_ms": audit_num("total-blocking-time"),
                        "fcp_ms": audit_num("first-contentful-paint"),
                        "tti_ms": audit_num("interactive"),
                        "field_metrics": metrics,
                        "lighthouse": {
                            "categories": {
                                "performance": cat_score("performance"),
                                "accessibility": cat_score("accessibility"),
                                "best_practices": cat_score("best-practices"),
                                "seo": cat_score("seo"),
                                "pwa": cat_score("pwa"),
                            },
                            "failed_audits": failed,
                        },
                    }
            except Exception:
                pass

        # No PSI key: return minimal structure; HTML will show "N/A"
        return {"source": "none", "strategy": strategy}

# -------------------------------------------------------------------
# Scoring Engine (aligned with front-end)
# -------------------------------------------------------------------
class ScoreEngine:
    CATEGORY_WEIGHTS = {"security": 0.28, "performance": 0.27, "seo": 0.23, "ux": 0.12, "crawl": 0.10}

    def score(self, crawl: Dict[str, Any]) -> Dict[str, Any]:
        pages = crawl.get("pages", [])
        cwv = crawl.get("cwv", {}) or {}

        totals = {
            "missing_titles": 0,
            "missing_meta_descriptions": 0,
            "missing_h1": 0,
            "broken_internal_links_total": 0,  # not sampled here; kept for UI parity
            "hsts_missing_pages": 0,
            "csp_missing_pages": 0,
            "mixed_content_pages": 0,
            "cookie_banner_pages": 0,
            "gzip_missing_pages": 0,
            "render_blocking_pages": 0,
            "schema_pages": 0,
            "alt_issues_pages": 0,
            "hreflang_pages": 0,
            "lang_attr_issue_pages": 0,
        }

        avg_response_time_ms = round(sum(p.get("response_time_ms", 0.0) for p in pages) / max(1, len(pages)), 2)
        avg_html_size_kb = round(sum(p.get("html_size_bytes", 0) for p in pages) / max(1, len(pages)) / 1024.0, 2)
        render_blocking_css_pages = sum(1 for p in pages if p.get("performance", {}).get("render_blocking_css_in_head", 0) > 0)
        totals["render_blocking_pages"] = render_blocking_css_pages

        titles_seen, meta_seen = {}, {}
        for p in pages:
            title = p.get("title")
            meta_desc = p.get("meta_description")
            if not title:
                totals["missing_titles"] += 1
            else:
                titles_seen[title] = titles_seen.get(title, 0) + 1
            if not meta_desc:
                totals["missing_meta_descriptions"] += 1
            else:
                meta_seen[meta_desc] = meta_seen.get(meta_desc, 0) + 1
            if not p.get("h1"):
                totals["missing_h1"] += 1

            sec = p.get("security", {})
            if p.get("status") == 200:
                if not sec.get("hsts") and sec.get("is_https"):
                    totals["hsts_missing_pages"] += 1
                if not sec.get("csp"):
                    totals["csp_missing_pages"] += 1
                if sec.get("mixed_content"):
                    totals["mixed_content_pages"] += 1

            if p.get("performance", {}).get("gzip_missing"):
                totals["gzip_missing_pages"] += 1

            if p.get("cookie_banner"):
                totals["cookie_banner_pages"] += 1

            # Accessibility: count pages with alt coverage < 80%
            alt_pct = p.get("accessibility", {}).get("alt_coverage_pct", 100.0)
            if alt_pct < 80.0:
                totals["alt_issues_pages"] += 1

            # Schema/i18n
            if p.get("seo", {}).get("schema_present"):
                totals["schema_pages"] += 1
            if (p.get("i18n", {}).get("hreflang") or []):
                totals["hreflang_pages"] += 1
            if p.get("i18n", {}).get("lang_attr_issues"):
                totals["lang_attr_issue_pages"] += 1

        duplicate_titles = sum(1 for v in titles_seen.values() if v > 1)
        duplicate_meta = sum(1 for v in meta_seen.values() if v > 1)

        # Totals breakdown
        total_errors = (
            totals["missing_titles"] + totals["missing_h1"] +
            totals["hsts_missing_pages"] + totals["csp_missing_pages"] +
            totals["mixed_content_pages"] + totals["alt_issues_pages"]
        )
        total_warnings = (
            totals["missing_meta_descriptions"] + totals["gzip_missing_pages"] +
            totals["render_blocking_pages"] + duplicate_titles + duplicate_meta +
            totals["lang_attr_issue_pages"]
        )
        total_notices = max(0, len(pages) - total_errors - total_warnings)

        # Subscores
        sec_score = 100
        sec_score -= min(45, totals["mixed_content_pages"] * 9)
        sec_score -= min(30, totals["hsts_missing_pages"] * 3)
        sec_score -= min(30, totals["csp_missing_pages"] * 3)

        perf_score = 100
        perf_score -= min(25, totals["gzip_missing_pages"] * 2)
        perf_score -= min(15, totals["render_blocking_pages"])
        perf_score -= min(25, max(0, (avg_response_time_ms - 800) / 100))
        perf_score -= min(20, max(0, (avg_html_size_kb - 120) / 20))
        if isinstance(cwv.get("lcp_ms"), (int, float)):
            perf_score -= min(25, max(0, (cwv["lcp_ms"] - 2500) / 150))
        if isinstance(cwv.get("tbt_ms"), (int, float)):
            perf_score -= min(20, max(0, (cwv["tbt_ms"] - 300) / 50))

        seo_score = 100
        seo_score -= min(25, totals["missing_titles"] * 2)
        seo_score -= min(20, totals["missing_meta_descriptions"])
        seo_score -= min(20, totals["missing_h1"] * 2)
        seo_score -= min(10, duplicate_titles)
        seo_score -= min(10, duplicate_meta)
        seo_score += min(5, totals["schema_pages"])  # small boost

        ux_score = 100
        pages_without_viewport = sum(1 for p in pages if not p.get("has_viewport"))
        ux_score -= min(25, pages_without_viewport * 3)
        if isinstance(cwv.get("cls"), (int, float)):
            ux_score -= min(20, max(0, (cwv["cls"] - 0.1) * 100))

        crawl_score = 100  # simplified (non-200 and broken links not fully sampled)

        overall = (
            sec_score * self.CATEGORY_WEIGHTS["security"] +
            perf_score * self.CATEGORY_WEIGHTS["performance"] +
            seo_score * self.CATEGORY_WEIGHTS["seo"] +
            ux_score * self.CATEGORY_WEIGHTS["ux"] +
            crawl_score * self.CATEGORY_WEIGHTS["crawl"]
        )
        overall_score = int(round(overall))

        grade, classification = self._grade(overall_score)
        risk_level = ("Critical" if overall_score < 60 else "At Risk" if overall_score < 75 else "Moderate" if overall_score < 85 else "Low")
        business_impact = (
            "High revenue risk due to security/performance gaps" if risk_level in ("Critical", "At Risk") else
            "Some conversion & SEO losses; address prioritized items" if risk_level == "Moderate" else
            "Healthy site; maintain and monitor"
        )
        compliance_readiness = max(0, min(100, sec_score - totals["mixed_content_pages"] * 2))

        return {
            "overall_score": overall_score,
            "grade": grade,
            "classification": classification,
            "summary": {
                "avg_response_time_ms": avg_response_time_ms,
                "avg_html_size_kb": avg_html_size_kb,
                "render_blocking_pages": {"css_in_head": totals["render_blocking_pages"]},
                "totals": {"errors": total_errors, "warnings": total_warnings, "notices": total_notices},
                "subscores": {
                    "security": round(sec_score, 1),
                    "performance": round(perf_score, 1),
                    "seo": round(seo_score, 1),
                    "ux": round(ux_score, 1),
                    "crawl": round(crawl_score, 1),
                },
                "risk_exposure": risk_level,
                "business_impact": business_impact,
                "compliance_readiness": round(compliance_readiness, 1),
                "cwv": cwv,
                "lighthouse": cwv.get("lighthouse"),
            },
            "counts": totals,
        }

    def _grade(self, score: int) -> Tuple[str, str]:
        if score >= 92:
            return "A+", "Enterprise-Ready"
        if score >= 85:
            return "A", "Excellent"
        if score >= 75:
            return "B", "Good (needs improvement)"
        if score >= 65:
            return "C", "Risky"
        return "D", "Critical"

    def build_executive_summary(self, url: str, score_payload: Dict[str, Any]) -> str:
        s = score_payload["summary"]
        subs = s["subscores"]
        weak = ", ".join([k.capitalize() for k, v in sorted(subs.items(), key=lambda kv: kv[1])[:2]])
        counts = score_payload["counts"]

        actions = []
        if counts["hsts_missing_pages"] or counts["csp_missing_pages"] or counts["mixed_content_pages"]:
            actions.append("Enforce HSTS, add a robust CSP, and remove mixed content to restore browser trust.")
        if counts["gzip_missing_pages"] or s["render_blocking_pages"]["css_in_head"] > 0:
            actions.append("Enable Brotli/Gzip and reduce render-blocking CSS; improve cache headers.")
        if counts["missing_titles"] or counts["missing_meta_descriptions"] or counts["missing_h1"]:
            actions.append("Complete & deduplicate titles/meta, and ensure a structured H1 per page.")
        if s.get("cwv", {}).get("lcp_ms"):
            actions.append("Reduce LCP by optimizing hero images, critical CSS, and lowering TTFB.")
        if s.get("lighthouse"):
            actions.append("Address Lighthouse findings across Performance, Accessibility, Best Practices, and SEO.")

        lines = [
            f"This audit of {url} evaluates security, performance, SEO, UX, crawl hygiene, and Lighthouse categories.",
            f"Overall score: {score_payload['overall_score']} ({score_payload['grade']}) — {score_payload['classification']}.",
            f"Avg response: {s['avg_response_time_ms']} ms, Avg HTML: {s['avg_html_size_kb']} KB.",
            f"Weak areas: {weak}.",
            "Top fixes:",
            " - " + "\n - ".join(actions) if actions else " - Maintain standards; continue monitoring.",
            "Prioritize security & performance, then SEO & UX to unlock conversions and growth.",
        ]
        text = " ".join([ln if isinstance(ln, str) else " ".join(ln) for ln in lines])
        words = text.split()
        if len(words) > 240:
            text = " ".join(words[:240])
        return text

# -------------------------------------------------------------------
# PDF Builder
# -------------------------------------------------------------------
def build_pdf_report(path: str, response: dict, crawl: dict):
    doc = SimpleDocTemplate(path, pagesize=A4, title="FF Tech - AI Website Audit")
    styles = getSampleStyleSheet()
    elements = []

    site = response.get("site") or crawl.get("site")
    elements.append(Paragraph("<b>FF Tech - AI Website Audit</b>", styles["Title"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Site: {site}", styles["Normal"]))
    elements.append(Paragraph(f"Grade: {response['result']['grade']} | Score: {response['result']['overall_score']}", styles["Normal"]))
    elements.append(Paragraph(f"Classification: {response['result']['classification']}", styles["Normal"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("<b>Executive Summary</b>", styles["Heading2"]))
    elements.append(Paragraph(response.get("summary", ""), styles["Normal"]))
    elements.append(Spacer(1, 12))

    subs = response["result"]["summary"]["subscores"]
    data = [["Category", "Score"]] + [[k.capitalize(), str(v)] for k, v in subs.items()]
    t = Table(data, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#667eea")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.25, colors.gray),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("BACKGROUND", (0,1), (-1,-1), colors.whitesmoke),
    ]))
    elements.append(Paragraph("<b>Category Subscores</b>", styles["Heading2"]))
    elements.append(t)
    elements.append(Spacer(1, 12))

    counts = response["result"]["counts"]
    data2 = [["Metric", "Count"],
             ["Missing Titles", str(counts["missing_titles"])],
             ["Missing Meta Descriptions", str(counts["missing_meta_descriptions"])],
             ["Missing H1", str(counts["missing_h1"])],
             ["HSTS Missing Pages", str(counts["hsts_missing_pages"])],
             ["CSP Missing Pages", str(counts["csp_missing_pages"])],
             ["Mixed Content Pages", str(counts["mixed_content_pages"])],
             ["Gzip/Brotli Missing Pages", str(counts["gzip_missing_pages"])],
             ["Render-blocking CSS pages", str(counts["render_blocking_pages"])],
             ["Accessibility ALT issues pages", str(counts.get("alt_issues_pages", 0))],
             ["Hreflang pages", str(counts.get("hreflang_pages", 0))],
             ["Lang attribute issues pages", str(counts.get("lang_attr_issue_pages", 0))],
             ]
    t2 = Table(data2, hAlign="LEFT")
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#764ba2")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.25, colors.gray),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("BACKGROUND", (0,1), (-1,-1), colors.whitesmoke),
    ]))
    elements.append(Paragraph("<b>Key Metrics</b>", styles["Heading2"]))
    elements.append(t2)

    s = response["result"]["summary"]
    cwv = s.get("cwv") or {}
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(
        f"Avg Response: {s['avg_response_time_ms']} ms | Avg HTML Size: {s['avg_html_size_kb']} KB | Render-blocking CSS pages: {s['render_blocking_pages']['css_in_head']}",
        styles["Normal"]
    ))
    lh = s.get("lighthouse") or {}
    if cwv.get("source") == "psi":
        cats = lh.get("categories") or {}
        elements.append(Paragraph(
            f"Lighthouse Performance: {cats.get('performance')} | Accessibility: {cats.get('accessibility')} | Best Practices: {cats.get('best_practices')} | SEO: {cats.get('seo')} | PWA: {cats.get('pwa')}",
            styles["Normal"]
        ))

    doc.build(elements)

# -------------------------------------------------------------------
# API Endpoints
# -------------------------------------------------------------------
@app.get("/")
async def root():
    """
    Optional: serve templates/index.html if present
    """
    try:
        with open("templates/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except Exception:
        return HTMLResponse("<h1>FF Tech — Backend is running.</h1><p>Place your HTML at templates/index.html to serve it here.</p>")

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@app.post("/audit/start")
async def audit_start(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url is required")

    # token accepted (ignored) to match front-end params
    # token = request.query_params.get("token")

    cfg = AuditConfig(
        url=url,
        deep=bool(payload.get("deep", True)),
        max_pages=int(payload.get("max_pages", 24)),
        respect_robots=bool(payload.get("respect_robots", True)),
        concurrency=int(payload.get("concurrency", 24)),
        user_agent=payload.get("user_agent") or "FFTechAuditBot/2.1",
        psi_strategy=payload.get("psi_strategy") or "mobile",
        link_check_sample_per_page=int(payload.get("link_check_sample_per_page", 25)),
        sitemap_max_depth=int(payload.get("sitemap_max_depth", 4)),
        sitemap_max_urls=int(payload.get("sitemap_max_urls", 50000)),
    )

    audit_id = hashlib.sha256(f"{url}|{time.time()}".encode()).hexdigest()[:16]

    engine = AuditEngine(cfg)
    try:
        crawl_result = await engine.run()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit failed: {e}")

    scorer = ScoreEngine()
    score_payload = scorer.score(crawl_result)
    summary = scorer.build_executive_summary(url, score_payload)

    response = {
        "site": url,
        "summary": summary,
        "result": score_payload,
        "created_at": datetime.utcnow().isoformat(),
    }

    AUDITS[audit_id] = {"config": cfg.to_dict(), "crawl": crawl_result, "response": response}
    init_db()
    save_audit(audit_id, url, response)

    return JSONResponse({"audit_id": audit_id})

@app.get("/audit/{audit_id}")
async def audit_get(audit_id: str):
    data = AUDITS.get(audit_id)
    if not data:
        raise HTTPException(status_code=404, detail="audit_id not found")
    return JSONResponse(data["response"])

@app.get("/audit/{audit_id}/pdf")
async def audit_pdf(audit_id: str):
    data = AUDITS.get(audit_id)
    if not data:
        raise HTTPException(status_code=404, detail="audit_id not found")
    os.makedirs("reports", exist_ok=True)
    pdf_path = f"reports/audit_{audit_id}.pdf"
    build_pdf_report(pdf_path, data["response"], data["crawl"])
    return JSONResponse({"status": "ok", "path": pdf_path})

@app.get("/audit/{site}/trend")
async def audit_trend(site: str, limit: int = 10):
    records = load_recent_audits(site, limit=limit)
    trend = [{
        "created_at": r.get("created_at"),
        "overall_score": r.get("result", {}).get("overall_score"),
        "grade": r.get("result", {}).get("grade"),
        "errors": r.get("result", {}).get("summary", {}).get("totals", {}).get("errors"),
        "warnings": r.get("result", {}).get("summary", {}).get("totals", {}).get("warnings"),
    } for r in records]
    return {"site": site, "trend": trend}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
