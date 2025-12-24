# -*- coding: utf-8 -*-
"""
Website Audit Tool (Single File)
--------------------------------
A comprehensive, single-file Python script that audits a modern website across
technical SEO, on-page SEO, performance, security, mobile usability, 
international SEO, and advanced metrics, and produces a JSON report with 
category scores and an overall classification (Excellent / Good / Needs Improvement / Poor).

Usage:
    python website_audit.py --url https://example.com --max-pages 100 --timeout 10

Optional:
    --pagespeed-api-key YOUR_KEY            # to fetch Core Web Vitals via PSI
    --include-external                      # also crawl external links (default: internal only)
    --output report.json                    # write JSON report to a file

Notes:
- This tool performs light crawling (BFS), respects domain boundaries by default.
- Some advanced metrics require external APIs (Google PageSpeed Insights, GSC, SEMrush). 
  Stub hooks are provided. If no API key is supplied, those metrics will be marked as "unavailable".
- Scoring is heuristic and transparent. Adjust weights as needed.

Author: M365 Copilot
"""

import argparse
import json
import re
import time
import urllib.parse as urlparse
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List, Set, Tuple

import requests
from bs4 import BeautifulSoup

# ---------------------------- Utility Functions ---------------------------- #

def normalize_url(base: str, link: str) -> str:
    """Resolve relative links, strip fragments, normalize scheme/host."""
    try:
        absolute = urlparse.urljoin(base, link)
        parsed = urlparse.urlparse(absolute)
        # Remove fragments
        parsed = parsed._replace(fragment="")
        # Normalize default ports
        netloc = parsed.netloc
        if netloc.endswith(":80") and parsed.scheme == "http":
            netloc = netloc[:-3]
        if netloc.endswith(":443") and parsed.scheme == "https":
            netloc = netloc[:-4]
        parsed = parsed._replace(netloc=netloc)
        return urlparse.urlunparse(parsed)
    except Exception:
        return link


def is_same_domain(start_url: str, candidate_url: str) -> bool:
    a = urlparse.urlparse(start_url)
    b = urlparse.urlparse(candidate_url)
    return (a.scheme == b.scheme) and (a.netloc == b.netloc)


def get_domain(url: str) -> str:
    p = urlparse.urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


# ---------------------------- Robots.txt Parsing --------------------------- #

def fetch_robots(domain: str, timeout: int) -> Dict[str, List[str]]:
    robots = {"disallow": [], "allow": []}
    try:
        resp = requests.get(urlparse.urljoin(domain, "/robots.txt"), timeout=timeout, headers={"User-Agent": "WebsiteAuditBot/1.0"})
        if resp.status_code == 200:
            for line in resp.text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.lower().startswith("disallow:"):
                    path = line.split(":", 1)[1].strip()
                    robots["disallow"].append(path)
                elif line.lower().startswith("allow:"):
                    path = line.split(":", 1)[1].strip()
                    robots["allow"].append(path)
    except Exception:
        pass
    return robots


def is_blocked_by_robots(robots: Dict[str, List[str]], url: str, domain: str) -> bool:
    # Very simple robots parsing (path-level). For production, use robots.txt parser.
    path = urlparse.urlparse(url).path or "/"
    disallows = robots.get("disallow", [])
    allows = robots.get("allow", [])
    for a in allows:
        if path.startswith(a):
            return False
    for d in disallows:
        if path.startswith(d):
            return True
    return False


# ---------------------------- Fetch & Parse ------------------------------- #

def fetch(url: str, timeout: int) -> Tuple[int, requests.Response, BeautifulSoup, Dict[str, str], float]:
    """Fetch URL and return (status, response, soup, headers, elapsed)."""
    headers = {"User-Agent": "WebsiteAuditBot/1.0"}
    start = time.time()
    try:
        resp = requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
        elapsed = time.time() - start
        status = resp.status_code
        content_type = resp.headers.get("Content-Type", "")
        soup = None
        if "text/html" in content_type.lower():
            soup = BeautifulSoup(resp.text, "html.parser")
        return status, resp, soup, resp.headers, elapsed
    except Exception:
        return 0, None, None, {}, 0.0


# ---------------------------- Audit Classes ------------------------------- #

class PageAudit:
    """Collect metrics for a single page."""
    def __init__(self, url: str):
        self.url = url
        self.metrics = {
            # Crawlability & Indexation
            "status_code": None,
            "redirect_chain_len": 0,
            "is_blocked_robots": False,
            "canonical": None,
            "canonical_missing": False,
            "canonical_incorrect": False,
            "meta_robots": None,
            "noindex": False,
            "nofollow": False,

            # On-Page SEO
            "title": None,
            "title_length": 0,
            "title_missing": False,
            "meta_description": None,
            "meta_description_length": 0,
            "meta_description_missing": False,
            "h1_count": 0,
            "h1_missing": False,
            "h2_h6_count": 0,
            "duplicate_headings": False,
            "word_count": 0,
            "thin_content": False,
            "images_without_alt": 0,
            "duplicate_alt_attrs": 0,
            "open_graph_present": False,
            "twitter_card_present": False,

            # URL & Internal Linking
            "url_length": 0,
            "url_has_uppercase": False,
            "internal_links": 0,
            "external_links": 0,
            "nofollow_internal_links": 0,
            "broken_internal_links": 0,
            "broken_external_links": 0,
            "anchor_issues": 0,

            # Technical & Performance
            "dom_elements": 0,
            "script_count": 0,
            "css_count": 0,
            "img_count": 0,
            "render_blocking": False,
            "lazy_loading_images": False,
            "uses_webp": False,
            "cache_control_present": False,
            "compression": None,  # gzip/brotli/none
            "ttfb": 0.0,

            # Mobile & Usability
            "viewport_present": False,

            # Security
            "https": False,
            "mixed_content": False,
            "security_headers": {
                "csp": False,
                "hsts": False,
                "x_frame_options": False,
            },
            "password_form_insecure": False,

            # International SEO
            "hreflang_tags": [],
            "hreflang_errors": 0,
        }

    def run(self, soup: BeautifulSoup, headers: Dict[str, str], resp: requests.Response, status: int, elapsed: float, robots: Dict[str, List[str]], domain: str):
        self.metrics["status_code"] = status
        self.metrics["redirect_chain_len"] = len(resp.history) if resp is not None else 0
        self.metrics["ttfb"] = elapsed
        self.metrics["https"] = self.url.lower().startswith("https://")
        self.metrics["is_blocked_robots"] = is_blocked_by_robots(robots, self.url, domain)

        if headers:
            enc = headers.get("Content-Encoding", "").lower()
            if "gzip" in enc:
                self.metrics["compression"] = "gzip"
            elif "br" in enc:
                self.metrics["compression"] = "brotli"
            else:
                self.metrics["compression"] = "none"
            self.metrics["cache_control_present"] = bool(headers.get("Cache-Control"))
            # Security Headers
            self.metrics["security_headers"]["csp"] = bool(headers.get("Content-Security-Policy"))
            self.metrics["security_headers"]["hsts"] = bool(headers.get("Strict-Transport-Security"))
            self.metrics["security_headers"]["x_frame_options"] = bool(headers.get("X-Frame-Options"))

        # Early return if not HTML
        if soup is None:
            return

        # Canonical
        link_canon = soup.find("link", rel=lambda v: v and "canonical" in v)
        if link_canon and link_canon.get("href"):
            self.metrics["canonical"] = normalize_url(self.url, link_canon.get("href"))
            # Incorrect if canonical points to different domain or non-normalized variant
            self.metrics["canonical_incorrect"] = not is_same_domain(self.url, self.metrics["canonical"])
        else:
            self.metrics["canonical_missing"] = True

        # Meta robots
        mr = soup.find("meta", attrs={"name": "robots"})
        if mr and mr.get("content"):
            content = mr.get("content", "").lower()
            self.metrics["meta_robots"] = content
            self.metrics["noindex"] = "noindex" in content
            self.metrics["nofollow"] = "nofollow" in content

        # Title & description
        title_tag = soup.title
        title_text = clean_text(title_tag.string) if title_tag and title_tag.string else ""
        self.metrics["title"] = title_text or None
        self.metrics["title_length"] = len(title_text)
        self.metrics["title_missing"] = (self.metrics["title"] is None)

        desc_tag = soup.find("meta", attrs={"name": "description"})
        desc_content = clean_text(desc_tag.get("content", "")) if desc_tag else ""
        self.metrics["meta_description"] = desc_content or None
        self.metrics["meta_description_length"] = len(desc_content)
        self.metrics["meta_description_missing"] = (self.metrics["meta_description"] is None)

        # Headings
        h1s = [clean_text(h.get_text()) for h in soup.find_all("h1")]
        self.metrics["h1_count"] = len(h1s)
        self.metrics["h1_missing"] = (len(h1s) == 0)
        h2_h6 = [clean_text(h.get_text()) for h in soup.find_all(["h2", "h3", "h4", "h5", "h6"])]
        self.metrics["h2_h6_count"] = len(h2_h6)
        self.metrics["duplicate_headings"] = len(h1s) != len(set(h1s)) or len(h2_h6) != len(set(h2_h6))

        # Content
        text = clean_text(soup.get_text(" "))
        self.metrics["word_count"] = len(text.split())
        self.metrics["thin_content"] = (self.metrics["word_count"] < 300)

        # Images
        images = soup.find_all("img")
        self.metrics["img_count"] = len(images)
        alt_values = []
        for img in images:
            alt = img.get("alt")
            if not alt:
                self.metrics["images_without_alt"] += 1
            else:
                alt_values.append(alt)
        self.metrics["duplicate_alt_attrs"] = len(alt_values) - len(set(alt_values))

        # Social metadata
        self.metrics["open_graph_present"] = bool(soup.find("meta", property=re.compile(r"^og:")))
        self.metrics["twitter_card_present"] = bool(soup.find("meta", attrs={"name": re.compile(r"^twitter:")}))

        # URL metrics
        self.metrics["url_length"] = len(self.url)
        self.metrics["url_has_uppercase"] = any(c.isupper() for c in urlparse.urlparse(self.url).path)

        # Links
        anchors = soup.find_all("a", href=True)
        internal, external, nofollow_internal = 0, 0, 0
        broken_internal, broken_external = 0, 0
        anchor_issues = 0
        for a in anchors:
            href = a.get("href")
            rel = (a.get("rel") or [])
            target_url = normalize_url(self.url, href)
            if is_same_domain(self.url, target_url):
                internal += 1
                if "nofollow" in [r.lower() for r in rel]:
                    nofollow_internal += 1
                # Broken anchor (#fragment) check on same page
                parsed = urlparse.urlparse(target_url)
                if parsed.fragment:
                    if not soup.find(id=parsed.fragment):
                        anchor_issues += 1
            else:
                external += 1
        self.metrics["internal_links"] = internal
        self.metrics["external_links"] = external
        self.metrics["nofollow_internal_links"] = nofollow_internal
        self.metrics["broken_internal_links"] = broken_internal
        self.metrics["broken_external_links"] = broken_external
        self.metrics["anchor_issues"] = anchor_issues

        # Technical (DOM, resources, render-blocking hints)
        self.metrics["dom_elements"] = len(soup.find_all(True))
        scripts = soup.find_all("script")
        self.metrics["script_count"] = len(scripts)
        css_links = soup.find_all("link", rel=lambda v: v and "stylesheet" in v)
        self.metrics["css_count"] = len(css_links)
        # Render blocking heuristic: many CSS in <head> and scripts without async/defer
        head = soup.find("head")
        rb = False
        if head:
            head_scripts = head.find_all("script")
            for s in head_scripts:
                if not s.get("async") and not s.get("defer"):
                    rb = True
                    break
            if len(css_links) > 2:
                rb = True
        self.metrics["render_blocking"] = rb

        # Lazy loading images & WebP usage
        self.metrics["lazy_loading_images"] = any((img.get("loading") == "lazy") or (img.get("data-src") or img.get("data-lazy")) for img in images)
        self.metrics["uses_webp"] = any((img.get("src") or "").lower().endswith(".webp") for img in images)

        # Mixed content (http resources on https pages)
        if self.metrics["https"]:
            http_resource_found = False
            for tag in soup.find_all(["img", "script", "link"]):
                src = tag.get("src") or tag.get("href")
                if src and normalize_url(self.url, src).startswith("http://"):
                    http_resource_found = True
                    break
            self.metrics["mixed_content"] = http_resource_found

        # Viewport
        self.metrics["viewport_present"] = bool(soup.find("meta", attrs={"name": "viewport"}))

        # Password forms on HTTP
        forms = soup.find_all("form")
        has_password = any(f.find("input", attrs={"type": "password"}) for f in forms)
        self.metrics["password_form_insecure"] = (has_password and not self.metrics["https"]) 

        # International SEO: hreflang
        hreflangs = soup.find_all("link", rel=lambda v: v and "alternate" in v)
        lang_errors = 0
        tags = []
        for hl in hreflangs:
            if hl.get("hreflang") and hl.get("href"):
                lang = hl.get("hreflang").lower()
                href = normalize_url(self.url, hl.get("href"))
                # Basic language code validation: xx or xx-YY
                if not re.match(r"^[a-z]{2}(-[a-zA-Z]{2})?$", lang):
                    lang_errors += 1
                tags.append({"hreflang": lang, "href": href})
        self.metrics["hreflang_tags"] = tags
        self.metrics["hreflang_errors"] = lang_errors


# ---------------------------- Site Audit & Scoring ------------------------ #

class WebsiteAudit:
    def __init__(self, base_url: str, max_pages: int = 100, timeout: int = 10, include_external: bool = False, pagespeed_api_key: str = None):
        self.base_url = base_url.rstrip("/")
        self.domain = get_domain(self.base_url)
        self.max_pages = max_pages
        self.timeout = timeout
        self.include_external = include_external
        self.pagespeed_api_key = pagespeed_api_key

        # Data stores
        self.visited: Set[str] = set()
        self.queue: deque = deque()
        self.incoming_links: defaultdict = defaultdict(int)  # URL -> incoming internal link count
        self.page_results: Dict[str, Dict] = {}

        # Robots
        self.robots = fetch_robots(self.domain, self.timeout)

        # Report structure
        self.report: Dict = {
            "meta": {
                "base_url": self.base_url,
                "domain": self.domain,
                "crawled_at": datetime.utcnow().isoformat() + "Z",
                "max_pages": self.max_pages,
                "timeout": self.timeout,
            },
            "site_health": {},
            "crawlability": {},
            "on_page_seo": {},
            "technical_performance": {},
            "mobile_usability": {},
            "security": {},
            "international_seo": {},
            "advanced_metrics": {},
            "trend_metrics": {"available": False},
            "scores": {},
            "overall": {"score": 0, "classification": ""},
            "pages": {},
            "recommendations": [],
        }

    def crawl(self):
        self.queue.append(self.base_url)
        while self.queue and len(self.visited) < self.max_pages:
            url = self.queue.popleft()
            if url in self.visited:
                continue
            self.visited.add(url)

            status, resp, soup, headers, elapsed = fetch(url, self.timeout)
            page_audit = PageAudit(url)
            page_audit.run(soup, headers, resp, status, elapsed, self.robots, self.domain)
            self.page_results[url] = page_audit.metrics

            # Extract links
            if soup:
                for a in soup.find_all("a", href=True):
                    target = normalize_url(url, a["href"]) 
                    # Skip mailto/tel/javascript
                    if target.startswith("mailto:") or target.startswith("tel:") or target.startswith("javascript:"):
                        continue
                    # Keep only HTTP(S)
                    if not target.startswith("http://") and not target.startswith("https://"):
                        continue
                    # Internal-only unless include_external
                    if not self.include_external and not is_same_domain(self.base_url, target):
                        continue
                    # Robots block
                    if is_blocked_by_robots(self.robots, target, self.domain):
                        continue
                    if target not in self.visited:
                        self.queue.append(target)
                    # Incoming internal links
                    if is_same_domain(self.base_url, target):
                        self.incoming_links[target] += 1

    # ------------------------ Aggregation Helpers ------------------------- #
    def aggregate(self):
        pages = self.page_results
        total = len(pages)
        self.report["meta"]["pages_crawled"] = total

        # Site health summary
        status_counts = defaultdict(int)
        redirects = 0
        robots_blocked = 0
        noindex_pages = 0
        for url, m in pages.items():
            sc = m.get("status_code", 0)
            if sc:
                status_counts[str(sc)] += 1
            if m.get("redirect_chain_len", 0) > 1:
                redirects += 1
            if m.get("is_blocked_robots"):
                robots_blocked += 1
            if m.get("noindex"):
                noindex_pages += 1
        self.report["site_health"] = {
            "status_distribution": status_counts,
            "redirect_chains": redirects,
            "robots_blocked_pages": robots_blocked,
            "noindex_pages": noindex_pages,
            "orphan_pages": max(0, total - len(self.incoming_links)),
        }

        # Crawlability
        missing_canon = sum(1 for m in pages.values() if m.get("canonical_missing"))
        incorrect_canon = sum(1 for m in pages.values() if m.get("canonical_incorrect"))
        self.report["crawlability"] = {
            "missing_canonical": missing_canon,
            "incorrect_canonical": incorrect_canon,
            "blocked_by_robots": robots_blocked,
            "broken_internal_links": sum(m.get("broken_internal_links", 0) for m in pages.values()),
            "broken_external_links": sum(m.get("broken_external_links", 0) for m in pages.values()),
        }

        # On-page SEO
        title_missing = sum(1 for m in pages.values() if m.get("title_missing"))
        desc_missing = sum(1 for m in pages.values() if m.get("meta_description_missing"))
        h1_missing = sum(1 for m in pages.values() if m.get("h1_missing"))
        thin_content = sum(1 for m in pages.values() if m.get("thin_content"))
        images_no_alt = sum(m.get("images_without_alt", 0) for m in pages.values())
        duplicate_alt = sum(m.get("duplicate_alt_attrs", 0) for m in pages.values())
        og_present = sum(1 for m in pages.values() if m.get("open_graph_present"))
        tw_present = sum(1 for m in pages.values() if m.get("twitter_card_present"))
        self.report["on_page_seo"] = {
            "missing_titles": title_missing,
            "missing_meta_descriptions": desc_missing,
            "missing_h1": h1_missing,
            "thin_content_pages": thin_content,
            "images_missing_alt": images_no_alt,
            "duplicate_alt_attributes": duplicate_alt,
            "open_graph_present_pages": og_present,
            "twitter_card_present_pages": tw_present,
        }

        # Technical performance (heuristics)
        avg_dom = sum(m.get("dom_elements", 0) for m in pages.values()) / total if total else 0
        avg_scripts = sum(m.get("script_count", 0) for m in pages.values()) / total if total else 0
        avg_css = sum(m.get("css_count", 0) for m in pages.values()) / total if total else 0
        avg_ttfb = sum(m.get("ttfb", 0.0) for m in pages.values()) / total if total else 0.0
        render_blocking_pages = sum(1 for m in pages.values() if m.get("render_blocking"))
        lazy_images_pages = sum(1 for m in pages.values() if m.get("lazy_loading_images"))
        webp_pages = sum(1 for m in pages.values() if m.get("uses_webp"))
        cache_control_pages = sum(1 for m in pages.values() if m.get("cache_control_present"))
        compression_none_pages = sum(1 for m in pages.values() if m.get("compression") == "none")
        self.report["technical_performance"] = {
            "avg_dom_elements": int(avg_dom),
            "avg_script_count": int(avg_scripts),
            "avg_css_count": int(avg_css),
            "avg_ttfb_seconds": round(avg_ttfb, 3),
            "render_blocking_pages": render_blocking_pages,
            "lazy_loading_images_pages": lazy_images_pages,
            "webp_usage_pages": webp_pages,
            "cache_control_present_pages": cache_control_pages,
            "no_compression_pages": compression_none_pages,
            "core_web_vitals": {"available": False},
        }

        # Mobile usability
        viewport_missing = sum(1 for m in pages.values() if not m.get("viewport_present"))
        self.report["mobile_usability"] = {
            "viewport_missing_pages": viewport_missing,
        }

        # Security
        https_pages = sum(1 for m in pages.values() if m.get("https"))
        mixed_content_pages = sum(1 for m in pages.values() if m.get("mixed_content"))
        csp_pages = sum(1 for m in pages.values() if m.get("security_headers", {}).get("csp"))
        hsts_pages = sum(1 for m in pages.values() if m.get("security_headers", {}).get("hsts"))
        xfo_pages = sum(1 for m in pages.values() if m.get("security_headers", {}).get("x_frame_options"))
        password_insecure_pages = sum(1 for m in pages.values() if m.get("password_form_insecure"))
        self.report["security"] = {
            "https_pages": https_pages,
            "mixed_content_pages": mixed_content_pages,
            "csp_header_pages": csp_pages,
            "hsts_header_pages": hsts_pages,
            "x_frame_options_header_pages": xfo_pages,
            "password_form_insecure_pages": password_insecure_pages,
        }

        # International SEO
        hreflang_errors_total = sum(m.get("hreflang_errors", 0) for m in pages.values())
        hreflang_pages = sum(1 for m in pages.values() if m.get("hreflang_tags"))
        self.report["international_seo"] = {
            "hreflang_pages": hreflang_pages,
            "hreflang_errors_total": hreflang_errors_total,
        }

        # Advanced metrics (selected subset)
        uppercase_urls = sum(1 for url, m in pages.items() if m.get("url_has_uppercase"))
        long_urls = sum(1 for url, m in pages.items() if m.get("url_length", 0) > 100)
        anchor_issues_pages = sum(1 for m in pages.values() if m.get("anchor_issues", 0) > 0)
        self.report["advanced_metrics"] = {
            "uppercase_urls": uppercase_urls,
            "long_urls_over_100_chars": long_urls,
            "anchor_issues_pages": anchor_issues_pages,
        }

        # Per-page dump
        self.report["pages"] = pages

    # ------------------------ Scoring Matrices ---------------------------- #
    def score(self):
        pages = self.page_results
        total = len(pages) or 1

        # Weights by category (sum to 100)
        weights = {
            "crawlability": 20,
            "on_page_seo": 20,
            "technical_performance": 20,
            "mobile_usability": 10,
            "security": 15,
            "international_seo": 5,
            "advanced_metrics": 10,
        }

        # Crawlability score (start at 100 and deduct)
        crawl_score = 100
        crawl_score -= 5 * min(10, self.report["crawlability"].get("missing_canonical", 0))
        crawl_score -= 5 * min(10, self.report["crawlability"].get("incorrect_canonical", 0))
        broken_int = self.report["crawlability"].get("broken_internal_links", 0)
        broken_ext = self.report["crawlability"].get("broken_external_links", 0)
        crawl_score -= min(30, broken_int // 5 * 2)
        crawl_score -= min(20, broken_ext // 10 * 1)
        blocked = self.report["crawlability"].get("blocked_by_robots", 0)
        crawl_score -= min(30, blocked * 2)
        crawl_score = max(0, min(100, crawl_score))

        # On-page SEO
        onpage_score = 100
        onpage_score -= min(30, self.report["on_page_seo"].get("missing_titles", 0) * 3)
        onpage_score -= min(30, self.report["on_page_seo"].get("missing_meta_descriptions", 0) * 2)
        onpage_score -= min(20, self.report["on_page_seo"].get("missing_h1", 0) * 2)
        onpage_score -= min(30, self.report["on_page_seo"].get("thin_content_pages", 0) * 1)
        images_no_alt = self.report["on_page_seo"].get("images_missing_alt", 0)
        onpage_score -= min(20, images_no_alt // 10)
        onpage_score = max(0, min(100, onpage_score))

        # Technical performance
        tech_score = 100
        avg_ttfb = self.report["technical_performance"].get("avg_ttfb_seconds", 0)
        if avg_ttfb > 1.0:
            tech_score -= 20
        if avg_ttfb > 2.0:
            tech_score -= 20
        rb_pages = self.report["technical_performance"].get("render_blocking_pages", 0)
        tech_score -= min(20, rb_pages)
        no_comp_pages = self.report["technical_performance"].get("no_compression_pages", 0)
        tech_score -= min(20, no_comp_pages)
        cache_pages = self.report["technical_performance"].get("cache_control_present_pages", 0)
        if cache_pages < total:
            tech_score -= 10
        tech_score = max(0, min(100, tech_score))

        # Mobile usability
        mob_score = 100
        viewport_missing = self.report["mobile_usability"].get("viewport_missing_pages", 0)
        mob_score -= min(50, viewport_missing * 10)
        mob_score = max(0, min(100, mob_score))

        # Security
        sec_score = 100
        mixed_pages = self.report["security"].get("mixed_content_pages", 0)
        sec_score -= min(40, mixed_pages * 10)
        pass_insec = self.report["security"].get("password_form_insecure_pages", 0)
        sec_score -= min(40, pass_insec * 20)
        hsts_pages = self.report["security"].get("hsts_header_pages", 0)
        if hsts_pages < total:
            sec_score -= 10
        sec_score = max(0, min(100, sec_score))

        # International
        intl_score = 100
        hreflang_err = self.report["international_seo"].get("hreflang_errors_total", 0)
        intl_score -= min(40, hreflang_err * 5)
        intl_score = max(0, min(100, intl_score))

        # Advanced metrics
        adv_score = 100
        long_urls = self.report["advanced_metrics"].get("long_urls_over_100_chars", 0)
        uppercase_urls = self.report["advanced_metrics"].get("uppercase_urls", 0)
        anchor_issue_pages = self.report["advanced_metrics"].get("anchor_issues_pages", 0)
        adv_score -= min(20, long_urls * 2)
        adv_score -= min(20, uppercase_urls * 2)
        adv_score -= min(20, anchor_issue_pages * 2)
        adv_score = max(0, min(100, adv_score))

        # Weighted overall
        weighted = (
            crawl_score * weights["crawlability"] +
            onpage_score * weights["on_page_seo"] +
            tech_score * weights["technical_performance"] +
            mob_score * weights["mobile_usability"] +
            sec_score * weights["security"] +
            intl_score * weights["international_seo"] +
            adv_score * weights["advanced_metrics"]
        ) / 100.0

        self.report["scores"] = {
            "crawlability": round(crawl_score, 1),
            "on_page_seo": round(onpage_score, 1),
            "technical_performance": round(tech_score, 1),
            "mobile_usability": round(mob_score, 1),
            "security": round(sec_score, 1),
            "international_seo": round(intl_score, 1),
            "advanced_metrics": round(adv_score, 1),
        }

        classification = (
            "Excellent" if weighted >= 90 else
            "Good" if weighted >= 70 else
            "Needs Improvement" if weighted >= 50 else
            "Poor"
        )
        self.report["overall"] = {"score": round(weighted, 1), "classification": classification}

    # ------------------------ Recommendations ---------------------------- #
    def build_recommendations(self):
        recs = []
        R = self.report
        if R["crawlability"].get("missing_canonical", 0) > 0:
            recs.append("Add canonical tags to pages missing them to consolidate signals.")
        if R["on_page_seo"].get("missing_titles", 0) > 0:
            recs.append("Write unique, descriptive <title> tags for all pages.")
        if R["on_page_seo"].get("missing_meta_descriptions", 0) > 0:
            recs.append("Add concise meta descriptions (120–160 chars) to improve CTR.")
        if R["on_page_seo"].get("images_missing_alt", 0) > 0:
            recs.append("Provide alt text for all images to improve accessibility and SEO.")
        if R["technical_performance"].get("render_blocking_pages", 0) > 0:
            recs.append("Defer or async non-critical JS and inline critical CSS to reduce render-blocking.")
        if R["technical_performance"].get("no_compression_pages", 0) > 0:
            recs.append("Enable GZIP/Brotli compression on the server for text assets.")
        if R["mobile_usability"].get("viewport_missing_pages", 0) > 0:
            recs.append("Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> for mobile responsiveness.")
        if R["security"].get("mixed_content_pages", 0) > 0:
            recs.append("Serve all assets over HTTPS to eliminate mixed content.")
        if R["security"].get("password_form_insecure_pages", 0) > 0:
            recs.append("Serve login forms over HTTPS and set Secure/HSTS headers.")
        if R["international_seo"].get("hreflang_errors_total", 0) > 0:
            recs.append("Fix hreflang codes (use formats like en, en-GB) and ensure reciprocal tags.")
        if R["advanced_metrics"].get("long_urls_over_100_chars", 0) > 0:
            recs.append("Shorten very long URLs; keep semantic, readable slugs.")
        self.report["recommendations"] = recs

    # ------------------------ Runner ------------------------------------- #
    def run(self):
        self.crawl()
        self.aggregate()
        self.score()
        self.build_recommendations()
        return self.report


# ---------------------------- CLI Entrypoint ------------------------------ #

def main():
    parser = argparse.ArgumentParser(description="Comprehensive Website Audit Tool (single-file)")
    parser.add_argument("--url", required=True, help="Base URL to audit, e.g., https://example.com")
    parser.add_argument("--max-pages", type=int, default=50, help="Max pages to crawl")
    parser.add_argument("--timeout", type=int, default=10, help="HTTP timeout in seconds")
    parser.add_argument("--include-external", action="store_true", help="Also crawl external links")
    parser.add_argument("--pagespeed-api-key", default=None, help="Google PageSpeed Insights API key (optional)")
    parser.add_argument("--output", default=None, help="Write report JSON to this file")
    args = parser.parse_args()

    audit = WebsiteAudit(
        base_url=args.url,
        max_pages=args.max_pages,
        timeout=args.timeout,
        include_external=args.include_external,
        pagespeed_api_key=args.pagespeed_api_key,
    )
    report = audit.run()

    text = json.dumps(report, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Report written to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
