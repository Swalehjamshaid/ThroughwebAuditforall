#!/usr/bin/env python3
"""
Web Audit Pro (Single File) — Updated
-------------------------------------
Adds:
- Executive PDF report (summary + charts via ReportLab + Matplotlib)
- Asynchronous crawling (asyncio + httpx if available; fallback to requests with thread offload)
- Google Search Console integration (indexed pages via Sitemaps API)
- SEMrush / Ahrefs integration placeholders (backlinks & authority)
- PageSpeed Insights enrichment, now with configurable strategy (mobile/desktop)

Usage:
  python web_audit_pro.py --url https://example.com --max-pages 100 --timeout 10 \
      --user-agent "WebAuditPro/1.0" --respect-robots --concurrency 20 \
      --pagespeed-api-key YOUR_PSI_KEY --pagespeed-strategy mobile \
      --gsc-credentials path/to/creds.json --gsc-property https://example.com/ \
      --semrush-key YOUR_SEMRUSH_KEY --ahrefs-key YOUR_AHREFS_KEY \
      --out audit_report.json --pdf-out audit_report.pdf

Notes:
- httpx is optional. If missing, the crawler uses requests under asyncio.to_thread.
- GSC Sitemaps listing requires site verification and proper OAuth credentials.
- SEMrush/Ahrefs integrations require paid API access; functions are stubs you can enable.
"""

import argparse
import asyncio
import json
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse
import urllib.robotparser as robotparser

import requests
from bs4 import BeautifulSoup

# Optional httpx for async crawling
try:
    import httpx  # type: ignore
    HAS_HTTPX = True
except Exception:
    HAS_HTTPX = False

# PDF & Charts
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Image
import matplotlib
matplotlib.use('Agg')  # headless backend
import matplotlib.pyplot as plt

# -------------------------------
# Data Structures
# -------------------------------
@dataclass
class PageMetrics:
    url: str
    status_code: Optional[int] = None
    final_url: Optional[str] = None
    redirect_chain: List[str] = field(default_factory=list)
    html_size_bytes: int = 0
    response_time_ms: Optional[int] = None
    title: Optional[str] = None
    meta_description: Optional[str] = None
    h1: List[str] = field(default_factory=list)
    headings: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))
    canonical: Optional[str] = None
    meta_robots: Optional[str] = None
    hreflang: List[Tuple[str, str]] = field(default_factory=list)  # (lang, href)
    og_tags_present: bool = False
    twitter_tags_present: bool = False
    structured_data_types: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    images_missing_alt: int = 0
    images_with_lazy_loading: int = 0
    has_webp_image: bool = False
    internal_links: List[str] = field(default_factory=list)
    external_links: List[str] = field(default_factory=list)
    anchor_issues: List[str] = field(default_factory=list)
    mixed_content_http_resources: List[str] = field(default_factory=list)
    has_viewport_meta: bool = False
    dom_nodes_estimate: int = 0
    render_blocking_css_in_head: int = 0
    render_blocking_js_in_head: int = 0
    third_party_scripts: int = 0
    cache_control_header: Optional[str] = None
    content_encoding: Optional[str] = None
    security_headers: Dict[str, Optional[str]] = field(default_factory=dict)
    open_directory_listing: bool = False
    has_login_form_insecure: bool = False

# -------------------------------
# Helper Functions
# -------------------------------

def is_same_domain(base: str, url: str) -> bool:
    try:
        return urlparse(base).netloc == urlparse(url).netloc
    except Exception:
        return False


def normalize_url(base: str, href: str) -> Optional[str]:
    try:
        abs_url = urljoin(base, href)
        parsed = urlparse(abs_url)
        if not parsed.scheme.startswith("http"):
            return None
        return abs_url.split('#')[0]
    except Exception:
        return None


def is_seo_friendly_url(url: str) -> bool:
    if len(url) > 100:
        return False
    path = urlparse(url).path
    if any(ch.isupper() for ch in path):
        return False
    if '_' in path:
        return False
    if urlparse(url).query and len(urlparse(url).query) > 100:
        return False
    return True


def count_dom_nodes(html: str) -> int:
    return html.count('<')


def extract_structured_data_types(soup: BeautifulSoup) -> List[str]:
    types = []
    for tag in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(tag.string or '{}')
            if isinstance(data, dict):
                t = data.get('@type')
                if t:
                    types.append(t)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get('@type'):
                        types.append(item['@type'])
        except Exception:
            continue
    return types


def parse_security_headers(headers: Dict[str, str]) -> Dict[str, Optional[str]]:
    keys = [
        'Content-Security-Policy', 'Strict-Transport-Security',
        'X-Frame-Options', 'X-Content-Type-Options', 'Referrer-Policy',
        'Permissions-Policy'
    ]
    return {k: headers.get(k) for k in keys}

# -------------------------------
# Async Auditor
# -------------------------------
class AsyncWebsiteAuditor:
    def __init__(self, base_url: str, max_pages: int = 50, timeout: int = 10,
                 user_agent: str = 'WebAuditPro/1.0', respect_robots: bool = True,
                 concurrency: int = 20, pagespeed_api_key: Optional[str] = None,
                 pagespeed_strategy: str = 'mobile'):
        self.base_url = base_url.rstrip('/')
        self.max_pages = max_pages
        self.timeout = timeout
        self.headers = {"User-Agent": user_agent}
        self.respect_robots = respect_robots
        self.pagespeed_api_key = pagespeed_api_key
        self.pagespeed_strategy = pagespeed_strategy.lower() if pagespeed_strategy in ('mobile','desktop') else 'mobile'
        self.visited: Set[str] = set()
        self.to_visit: asyncio.Queue[str] = asyncio.Queue()
        self.pages: Dict[str, PageMetrics] = {}
        self.concurrency = max(1, concurrency)
        self.sem = asyncio.Semaphore(self.concurrency)
        self.robots = robotparser.RobotFileParser()
        self.robots.set_url(urljoin(self.base_url, '/robots.txt'))
        try:
            self.robots.read()
        except Exception:
            pass

    def allowed_by_robots(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        try:
            return self.robots.can_fetch(self.headers['User-Agent'], url)
        except Exception:
            return True

    async def fetch_httpx(self, client: 'httpx.AsyncClient', url: str):
        try:
            start = time.time()
            resp = await client.get(url, timeout=self.timeout, follow_redirects=True)
            elapsed_ms = int((time.time() - start) * 1000)
            return resp, elapsed_ms
        except Exception:
            return None

    async def fetch_requests_threaded(self, url: str):
        def _do_get(u):
            start = time.time()
            r = requests.get(u, timeout=self.timeout, allow_redirects=True, headers=self.headers)
            return r, int((time.time() - start) * 1000)
        try:
            return await asyncio.to_thread(_do_get, url)
        except Exception:
            return None

    async def worker(self):
        client = None
        if HAS_HTTPX:
            client = httpx.AsyncClient(headers=self.headers)
        while len(self.visited) < self.max_pages:
            try:
                url = await asyncio.wait_for(self.to_visit.get(), timeout=1.0)
            except asyncio.TimeoutError:
                break
            if url in self.visited:
                continue
            if not self.allowed_by_robots(url):
                self.visited.add(url)
                self.pages[url] = PageMetrics(url=url, status_code=None)
                continue
            async with self.sem:
                result = None
                if HAS_HTTPX and client is not None:
                    result = await self.fetch_httpx(client, url)
                else:
                    result = await self.fetch_requests_threaded(url)
                metrics = PageMetrics(url=url)
                if result is None:
                    self.visited.add(url)
                    self.pages[url] = metrics
                    continue
                resp, elapsed_ms = result
                if HAS_HTTPX and 'httpx' in str(type(resp)):
                    text = resp.text
                    headers = resp.headers
                    status_code = resp.status_code
                    final_url = str(resp.url)
                    history = resp.history
                else:
                    text = resp.text
                    headers = resp.headers
                    status_code = resp.status_code
                    final_url = str(resp.url)
                    history = resp.history
                metrics.status_code = status_code
                metrics.response_time_ms = elapsed_ms
                metrics.final_url = final_url
                metrics.redirect_chain = [getattr(h, 'url', getattr(getattr(h, 'request', None), 'url', final_url)) for h in history] + [final_url]
                metrics.html_size_bytes = len(text or '')
                metrics.content_encoding = headers.get('Content-Encoding')
                metrics.cache_control_header = headers.get('Cache-Control')
                metrics.security_headers = parse_security_headers(headers)

                soup = BeautifulSoup(text, 'html.parser')
                metrics.title = soup.title.string.strip() if soup.title and soup.title.string else None
                md = soup.find('meta', attrs={'name': 'description'})
                metrics.meta_description = (md.get('content').strip() if md and md.get('content') else None)

                for level in ['h1','h2','h3','h4','h5','h6']:
                    tags = [t.get_text(strip=True) for t in soup.find_all(level)]
                    if level == 'h1':
                        metrics.h1 = tags
                    metrics.headings[level] = tags

                canon = soup.find('link', rel='canonical')
                metrics.canonical = canon.get('href') if canon and canon.get('href') else None

                robots_meta = soup.find('meta', attrs={'name': 'robots'})
                metrics.meta_robots = robots_meta.get('content') if robots_meta and robots_meta.get('content') else None

                for link in soup.find_all('link', rel='alternate'):
                    if link.get('hreflang') and link.get('href'):
                        metrics.hreflang.append((link.get('hreflang'), link.get('href')))

                metrics.og_tags_present = bool(soup.find('meta', property=re.compile(r'^og:')))
                metrics.twitter_tags_present = bool(soup.find('meta', attrs={'name': re.compile(r'^twitter:')}))
                metrics.structured_data_types = extract_structured_data_types(soup)

                imgs = soup.find_all('img')
                metrics.images = []
                metrics.images_missing_alt = 0
                metrics.images_with_lazy_loading = 0
                has_webp = False
                for img in imgs:
                    src = img.get('src') or img.get('data-src')
                    if src:
                        nsrc = normalize_url(url, src)
                        if nsrc:
                            metrics.images.append(nsrc)
                            if nsrc.lower().endswith('.webp'):
                                has_webp = True
                    alt = img.get('alt')
                    if not alt or alt.strip() == '':
                        metrics.images_missing_alt += 1
                    if (img.get('loading') or '').lower() == 'lazy':
                        metrics.images_with_lazy_loading += 1
                metrics.has_webp_image = has_webp

                anchors = soup.find_all('a', href=True)
                for a in anchors:
                    href = a['href']
                    nurl = normalize_url(url, href)
                    if not nurl:
                        continue
                    text_a = a.get_text(strip=True) or ''
                    if is_same_domain(self.base_url, nurl):
                        metrics.internal_links.append(nurl)
                    else:
                        metrics.external_links.append(nurl)
                    if len(text_a) <= 2:
                        metrics.anchor_issues.append('Very short anchor text')
                    if re.search(r'click here|read more', text_a, flags=re.I):
                        metrics.anchor_issues.append('Generic anchor text')

                if urlparse(metrics.final_url or url).scheme == 'https':
                    for tag in soup.find_all(src=True):
                        src = normalize_url(url, tag.get('src'))
                        if src and urlparse(src).scheme == 'http':
                            metrics.mixed_content_http_resources.append(src)
                    for tag in soup.find_all(href=True):
                        href = normalize_url(url, tag.get('href'))
                        if href and urlparse(href).scheme == 'http':
                            metrics.mixed_content_http_resources.append(href)

                viewport = soup.find('meta', attrs={'name': 'viewport'})
                metrics.has_viewport_meta = bool(viewport)

                metrics.dom_nodes_estimate = count_dom_nodes(text)

                head = soup.find('head')
                if head:
                    for link in head.find_all('link', rel='stylesheet'):
                        metrics.render_blocking_css_in_head += 1
                    for script in head.find_all('script', src=True):
                        attrs = script.attrs
                        if not ('defer' in attrs or 'async' in attrs):
                            metrics.render_blocking_js_in_head += 1

                for script in soup.find_all('script', src=True):
                    ssrc = normalize_url(url, script.get('src'))
                    if ssrc and not is_same_domain(self.base_url, ssrc):
                        metrics.third_party_scripts += 1

                title_text = metrics.title or ''
                metrics.open_directory_listing = title_text.lower().startswith('index of')
                if urlparse(url).scheme == 'http':
                    forms = soup.find_all('form')
                    for f in forms:
                        if f.find('input', attrs={'type':'password'}):
                            metrics.has_login_form_insecure = True
                            break

                self.pages[url] = metrics
                self.visited.add(url)

                for link in metrics.internal_links:
                    if link not in self.visited and link not in [i for i in self._queue_snapshot()] and len(self.visited) + self.to_visit.qsize() < self.max_pages:
                        await self.to_visit.put(link)

        if HAS_HTTPX and client is not None:
            await client.aclose()

    def _queue_snapshot(self) -> List[str]:
        try:
            return list(self.to_visit._queue)  # type: ignore
        except Exception:
            return []

    async def crawl(self):
        await self.to_visit.put(self.base_url)
        workers = [asyncio.create_task(self.worker()) for _ in range(self.concurrency)]
        await asyncio.gather(*workers)

    def aggregate(self) -> Dict:
        report = {
            'site': self.base_url,
            'summary': {},
            'counts': {},
            'recommendations': [],
            'category_scores': {},
            'overall_score': 0,
            'classification': ''
        }
        total_pages = len(self.pages)
        codes = Counter([p.status_code for p in self.pages.values() if p.status_code])
        errors_4xx = sum(v for k,v in codes.items() if k and 400 <= k < 500)
        errors_5xx = sum(v for k,v in codes.items() if k and 500 <= k < 600)

        broken_internal_links = 0
        redirect_chains = 0
        blocked_by_robots = 0
        for url, pm in self.pages.items():
            if pm.status_code is None:
                if self.respect_robots and not self.allowed_by_robots(url):
                    blocked_by_robots += 1
            if pm.status_code and pm.status_code in (404, 410):
                broken_internal_links += 1
            if pm.redirect_chain and len(pm.redirect_chain) > 2:
                redirect_chains += 1

        missing_titles = sum(1 for p in self.pages.values() if not p.title)
        missing_meta_desc = sum(1 for p in self.pages.values() if not p.meta_description)
        multiple_h1 = sum(1 for p in self.pages.values() if len(p.h1) > 1)
        missing_h1 = sum(1 for p in self.pages.values() if len(p.h1) == 0)
        long_urls = sum(1 for u in self.pages if len(u) > 100)
        uppercase_in_urls = sum(1 for u in self.pages if any(ch.isupper() for ch in urlparse(u).path))
        non_seo_friendly = sum(1 for u in self.pages if not is_seo_friendly_url(u))
        images_missing_alt_total = sum(p.images_missing_alt for p in self.pages.values())
        pages_without_og = sum(1 for p in self.pages.values() if not p.og_tags_present)
        pages_without_twitter = sum(1 for p in self.pages.values() if not p.twitter_tags_present)

        avg_html_kb = int(sum(p.html_size_bytes for p in self.pages.values()) / (total_pages or 1) / 1024)
        avg_dom_nodes = int(sum(p.dom_nodes_estimate for p in self.pages.values()) / (total_pages or 1))
        avg_resp_ms = int(sum(p.response_time_ms or 0 for p in self.pages.values()) / (total_pages or 1))
        render_blocking_css_pages = sum(1 for p in self.pages.values() if p.render_blocking_css_in_head > 0)
        render_blocking_js_pages = sum(1 for p in self.pages.values() if p.render_blocking_js_in_head > 0)
        third_party_script_heavy = sum(1 for p in self.pages.values() if p.third_party_scripts >= 5)
        gzip_missing = sum(1 for p in self.pages.values() if (p.content_encoding or '').lower() not in ('gzip','br'))

        viewport_missing_pages = sum(1 for p in self.pages.values() if not p.has_viewport_meta)

        https_implemented = self.base_url.startswith('https')
        mixed_content_pages = sum(1 for p in self.pages.values() if len(p.mixed_content_http_resources) > 0)
        hsts_missing_pages = sum(1 for p in self.pages.values() if not p.security_headers.get('Strict-Transport-Security'))
        csp_missing_pages = sum(1 for p in self.pages.values() if not p.security_headers.get('Content-Security-Policy'))
        xfo_missing_pages = sum(1 for p in self.pages.values() if not p.security_headers.get('X-Frame-Options'))
        open_dir_pages = sum(1 for p in self.pages.values() if p.open_directory_listing)
        insecure_login_pages = sum(1 for p in self.pages.values() if p.has_login_form_insecure)

        hreflang_missing_pages = sum(1 for p in self.pages.values() if len(p.hreflang) == 0)

        report['summary'] = {
            'total_crawled_pages': total_pages,
            'http_status_counts': dict(codes),
            'avg_html_size_kb': avg_html_kb,
            'avg_response_time_ms': avg_resp_ms,
            'avg_dom_nodes_estimate': avg_dom_nodes,
        }
        report['counts'] = {
            'errors_4xx': errors_4xx,
            'errors_5xx': errors_5xx,
            'broken_internal_links': broken_internal_links,
            'redirect_chains': redirect_chains,
            'blocked_by_robots': blocked_by_robots,
            'missing_titles': missing_titles,
            'missing_meta_descriptions': missing_meta_desc,
            'missing_h1': missing_h1,
            'multiple_h1': multiple_h1,
            'long_urls': long_urls,
            'uppercase_in_urls': uppercase_in_urls,
            'non_seo_friendly_urls': non_seo_friendly,
            'images_missing_alt_total': images_missing_alt_total,
            'pages_without_og': pages_without_og,
            'pages_without_twitter': pages_without_twitter,
            'render_blocking_css_pages': render_blocking_css_pages,
            'render_blocking_js_pages': render_blocking_js_pages,
            'third_party_script_heavy_pages': third_party_script_heavy,
            'gzip_missing_pages': gzip_missing,
            'viewport_missing_pages': viewport_missing_pages,
            'mixed_content_pages': mixed_content_pages,
            'hsts_missing_pages': hsts_missing_pages,
            'csp_missing_pages': csp_missing_pages,
            'xfo_missing_pages': xfo_missing_pages,
            'open_directory_listing_pages': open_dir_pages,
            'insecure_login_pages': insecure_login_pages,
            'hreflang_missing_pages': hreflang_missing_pages,
        }

        weights = {
            'site_health': 0.20,
            'crawlability': 0.20,
            'on_page_seo': 0.20,
            'technical_performance': 0.20,
            'mobile_usability': 0.10,
            'security': 0.10
        }

        bad_rate = (errors_4xx + errors_5xx) / (total_pages or 1)
        site_health_score = 100 - min(60, int(bad_rate * 100))
        site_health_score -= 20 if avg_resp_ms > 1500 else (10 if avg_resp_ms > 800 else 0)
        report['category_scores']['site_health'] = max(0, site_health_score)

        crawlability_score = 100
        crawlability_score -= min(40, redirect_chains * 5)
        crawlability_score -= min(40, broken_internal_links * 5)
        crawlability_score -= min(20, blocked_by_robots * 2)
        report['category_scores']['crawlability'] = max(0, crawlability_score)

        onpage_score = 100
        onpage_score -= min(30, int((missing_titles / (total_pages or 1))*100))
        onpage_score -= min(30, int((missing_meta_desc / (total_pages or 1))*100))
        onpage_score -= min(10, int((missing_h1 / (total_pages or 1))*100))
        onpage_score -= min(10, int((multiple_h1 / (total_pages or 1))*100))
        onpage_score -= min(10, int((non_seo_friendly / (total_pages or 1))*100))
        report['category_scores']['on_page_seo'] = max(0, onpage_score)

        tech_score = 100
        tech_score -= 20 if avg_html_kb > 1200 else (10 if avg_html_kb > 300 else 0)
        tech_score -= 20 if avg_dom_nodes > 5000 else (10 if avg_dom_nodes > 2000 else 0)
        tech_score -= min(20, render_blocking_css_pages * 3)
        tech_score -= min(20, render_blocking_js_pages * 3)
        tech_score -= min(20, third_party_script_heavy * 2)
        tech_score -= min(20, gzip_missing * 2)
        report['category_scores']['technical_performance'] = max(0, tech_score)

        mobile_score = 100 - min(30, int((viewport_missing_pages / (total_pages or 1))*100))
        report['category_scores']['mobile_usability'] = max(0, mobile_score)

        security_score = 100
        if not https_implemented:
            security_score -= 40
        security_score -= min(20, mixed_content_pages * 5)
        security_score -= min(20, hsts_missing_pages * 2)
        security_score -= min(20, csp_missing_pages * 2)
        security_score -= min(20, xfo_missing_pages * 2)
        security_score -= min(20, open_dir_pages * 5)
        security_score -= min(20, insecure_login_pages * 10)
        report['category_scores']['security'] = max(0, security_score)

        overall = 0
        for cat, sc in report['category_scores'].items():
            overall += sc * weights[cat]
        report['overall_score'] = round(overall, 2)
        report['summary']['good_vs_bad'] = 'Good' if overall >= 70 else 'Bad'
        report['classification'] = (
            'Excellent' if overall >= 90 else (
                'Good' if overall >= 70 else (
                    'Needs Improvement' if overall >= 50 else 'Poor')))

        recs = []
        if missing_titles or missing_meta_desc:
            recs.append('Add unique, optimized titles and meta descriptions to all pages.')
        if missing_h1 or multiple_h1:
            recs.append('Ensure exactly one descriptive H1 per page; fix missing or multiple H1s.')
        if non_seo_friendly:
            recs.append('Normalize URLs: use lowercase, short paths, hyphens; avoid long query strings.')
        if render_blocking_css_pages or render_blocking_js_pages:
            recs.append('Minimize render-blocking resources: inline critical CSS; use defer/async for JS.')
        if gzip_missing:
            recs.append('Enable server-side compression (GZIP/Brotli) and proper Cache-Control headers.')
        if viewport_missing_pages:
            recs.append('Add responsive <meta name="viewport"> to all templates.')
        if not https_implemented:
            recs.append('Serve the entire site over HTTPS with a valid certificate.')
        if mixed_content_pages:
            recs.append('Remove mixed content by upgrading all resources to HTTPS.')
        if hsts_missing_pages:
            recs.append('Enable HSTS (Strict-Transport-Security) to enforce HTTPS.')
        if csp_missing_pages:
            recs.append('Add a Content-Security-Policy to mitigate XSS; tighten sources.')
        if xfo_missing_pages:
            recs.append('Add X-Frame-Options/Frame-ancestors to prevent clickjacking.')
        if images_missing_alt_total:
            recs.append('Provide meaningful alt text for images to improve accessibility and SEO.')
        if third_party_script_heavy:
            recs.append('Audit and reduce third-party scripts; load asynchronously and after interaction.')
        report['recommendations'] = recs

        pages_snapshot = []
        for u, p in self.pages.items():
            pages_snapshot.append({
                'url': u,
                'status_code': p.status_code,
                'title': p.title,
                'meta_description': p.meta_description,
                'h1_count': len(p.h1),
                'canonical': p.canonical,
                'meta_robots': p.meta_robots,
                'og_tags_present': p.og_tags_present,
                'twitter_tags_present': p.twitter_tags_present,
                'structured_data_types': p.structured_data_types,
                'images_missing_alt': p.images_missing_alt,
                'images_with_lazy_loading': p.images_with_lazy_loading,
                'has_webp_image': p.has_webp_image,
                'internal_links_count': len(p.internal_links),
                'external_links_count': len(p.external_links),
                'render_blocking_css_in_head': p.render_blocking_css_in_head,
                'render_blocking_js_in_head': p.render_blocking_js_in_head,
                'third_party_scripts': p.third_party_scripts,
                'mixed_content_http_resources_count': len(p.mixed_content_http_resources),
                'has_viewport_meta': p.has_viewport_meta,
                'dom_nodes_estimate': p.dom_nodes_estimate,
                'cache_control_header': p.cache_control_header,
                'content_encoding': p.content_encoding,
                'security_headers': p.security_headers,
                'open_directory_listing': p.open_directory_listing,
                'has_login_form_insecure': p.has_login_form_insecure
            })
        report['pages'] = pages_snapshot
        return report

    def enrich_with_pagespeed(self, report: Dict):
        if not self.pagespeed_api_key:
            report['pagespeed'] = {'status': 'not_configured'}
            return
        try:
            api = (
                'https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url='
                + requests.utils.quote(self.base_url)
                + '&category=PERFORMANCE&strategy=' + self.pagespeed_strategy
                + '&key=' + self.pagespeed_api_key
            )
            resp = requests.get(api, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                lighthouse = data.get('lighthouseResult', {})
                perf_score = lighthouse.get('categories', {}).get('performance', {}).get('score', 0)
                audits = lighthouse.get('audits', {})
                lcp = audits.get('largest-contentful-paint', {}).get('numericValue')
                cls = audits.get('cumulative-layout-shift', {}).get('numericValue')
                tbt = audits.get('total-blocking-time', {}).get('numericValue')
                report['pagespeed'] = {
                    'performance_score': perf_score,
                    'lcp_ms': lcp,
                    'cls': cls,
                    'tbt_ms': tbt,
                    'strategy': self.pagespeed_strategy
                }
                if perf_score:
                    report['category_scores']['technical_performance'] = min(
                        100,
                        report['category_scores']['technical_performance'] + int(perf_score * 10)
                    )
                    weights = {
                        'site_health': 0.20,
                        'crawlability': 0.20,
                        'on_page_seo': 0.20,
                        'technical_performance': 0.20,
                        'mobile_usability': 0.10,
                        'security': 0.10
                    }
                    overall = 0
                    for cat, sc in report['category_scores'].items():
                        overall += sc * weights[cat]
                    report['overall_score'] = round(overall, 2)
                    report['summary']['good_vs_bad'] = 'Good' if overall >= 70 else 'Bad'
                    report['classification'] = (
                        'Excellent' if overall >= 90 else (
                            'Good' if overall >= 70 else (
                                'Needs Improvement' if overall >= 50 else 'Poor')))
            else:
                report['pagespeed'] = {'status': f'error {resp.status_code}'}
        except Exception as e:
            report['pagespeed'] = {'status': f'error: {e}'}

# -------------------------------
# Integrations: GSC, SEMrush, Ahrefs
# -------------------------------
class GSCClient:
    def __init__(self, credentials_json: Optional[str], timeout: int = 10):
        self.credentials_json = credentials_json
        self.timeout = timeout

    def fetch_indexed_from_sitemaps(self, property_url: str) -> Dict:
        if not self.credentials_json:
            return {'status': 'not_configured'}
        try:
            from google.oauth2 import service_account  # type: ignore
            from googleapiclient.discovery import build  # type: ignore
            SCOPES = ['https://www.googleapis.com/auth/webmasters.readonly']
            creds = service_account.Credentials.from_service_account_file(
                self.credentials_json, scopes=SCOPES)
            service = build('webmasters', 'v3', credentials=creds)
            sitemaps = service.sitemaps().list(siteUrl=property_url).execute()
            total_indexed = 0
            total_submitted = 0
            for sm in sitemaps.get('sitemap', []):
                for c in sm.get('contents', []):
                    total_indexed += int(c.get('indexed', 0))
                    total_submitted += int(c.get('submitted', 0))
            return {
                'status': 'ok',
                'indexed_pages_estimate': total_indexed,
                'submitted_pages_estimate': total_submitted
            }
        except Exception as e:
            return {'status': f'error: {e}'}

class BacklinksClient:
    def __init__(self, semrush_key: Optional[str], ahrefs_key: Optional[str], timeout: int = 10):
        self.semrush_key = semrush_key
        self.ahrefs_key = ahrefs_key
        self.timeout = timeout

    def fetch_domain_authority(self, domain: str) -> Dict:
        if not (self.semrush_key or self.ahrefs_key):
            return {'status': 'not_configured'}
        data = {'status': 'partial'}
        try:
            if self.semrush_key:
                data['semrush'] = {'note': 'Implement SEMrush endpoint with your plan params.'}
            if self.ahrefs_key:
                data['ahrefs'] = {'note': 'Implement Ahrefs endpoint with your token & parameters.'}
        except Exception as e:
            data['error'] = str(e)
        return data

# -------------------------------
# Executive Summary PDF
# -------------------------------
class ExecutiveSummaryPDF:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.story = []
        self.styles = getSampleStyleSheet()

    def add_title(self, site: str, overall_score: float, classification: str):
        title = "Website Audit Executive Summary"
        subtitle = f"Site: {site} | Overall Score: {overall_score} | Classification: {classification}"
        self.story.append(Paragraph(f"<para align=left><b>{title}</b></para>", self.styles['Title']))
        self.story.append(Spacer(1, 0.3*cm))
        self.story.append(Paragraph(subtitle, self.styles['Normal']))
        self.story.append(Spacer(1, 0.3*cm))

    def add_kpis(self, summary: Dict, counts: Dict):
        bullets = [
            f"Total Crawled Pages: {summary.get('total_crawled_pages', 0)}",
            f"Avg Response Time (ms): {summary.get('avg_response_time_ms', 0)}",
            f"Avg HTML Size (KB): {summary.get('avg_html_size_kb', 0)}",
            f"4xx Errors: {counts.get('errors_4xx', 0)}",
            f"5xx Errors: {counts.get('errors_5xx', 0)}",
            f"Missing Titles: {counts.get('missing_titles', 0)}",
            f"Missing Meta Descriptions: {counts.get('missing_meta_descriptions', 0)}",
            f"Viewport Missing Pages: {counts.get('viewport_missing_pages', 0)}",
            f"Mixed Content Pages: {counts.get('mixed_content_pages', 0)}",
        ]
        text = '<br/>'.join([f"• {b}" for b in bullets])
        self.story.append(Paragraph(text, self.styles['Normal']))
        self.story.append(Spacer(1, 0.3*cm))

    def add_recommendations(self, recs: List[str]):
        if not recs:
            return
        self.story.append(Paragraph('<b>Top Recommendations</b>', self.styles['Heading2']))
        text = '<br/>'.join([f"• {r}" for r in recs[:10]])
        self.story.append(Paragraph(text, self.styles['Normal']))
        self.story.append(Spacer(1, 0.3*cm))

    def add_chart_image(self, img_path: str, title: str):
        self.story.append(Paragraph(f"<b>{title}</b>", self.styles['Heading2']))
        try:
            self.story.append(Image(img_path, width=16*cm, height=9*cm))
        except Exception:
            self.story.append(Paragraph('Chart unavailable.', self.styles['Italic']))
        self.story.append(Spacer(1, 0.4*cm))

    def build(self):
        doc = SimpleDocTemplate(self.pdf_path, pagesize=A4)
        doc.build(self.story)

    @staticmethod
    def make_category_scores_chart(category_scores: Dict[str, float], out_path: str):
        cats = list(category_scores.keys())
        vals = [category_scores[k] for k in cats]
        plt.figure(figsize=(8, 4.5))
        plt.bar(cats, vals, color='#0078D4')
        plt.ylim(0, 100)
        plt.title('Category Scores (0–100)')
        plt.ylabel('Score')
        plt.xticks(rotation=30, ha='right')
        plt.tight_layout()
        plt.savefig(out_path)
        plt.close()

    @staticmethod
    def make_top_issues_chart(counts: Dict[str, int], out_path: str, topn: int = 10):
        pairs = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        labels = [k for k,_ in pairs[:topn]]
        values = [v for _,v in pairs[:topn]]
        plt.figure(figsize=(8, 4.5))
        plt.barh(labels[::-1], values[::-1], color='#F25022')
        plt.title('Top Issues by Count')
        plt.xlabel('Count')
        plt.tight_layout()
        plt.savefig(out_path)
        plt.close()

# -------------------------------
# CLI & Orchestration
# -------------------------------

def main():
    parser = argparse.ArgumentParser(description='Web Audit Pro — Async crawler + PDF + API integrations')
    parser.add_argument('--url', required=True, help='Base URL to audit (e.g., https://example.com)')
    parser.add_argument('--max-pages', type=int, default=100, help='Maximum pages to crawl')
    parser.add_argument('--timeout', type=int, default=10, help='HTTP timeout (seconds)')
    parser.add_argument('--user-agent', default='WebAuditPro/1.0', help='Crawler User-Agent')
    parser.add_argument('--respect-robots', action='store_true', help='Respect robots.txt (default off)')
    parser.add_argument('--concurrency', type=int, default=20, help='Async concurrency')
    parser.add_argument('--pagespeed-api-key', default=None, help='Google PSI API key (optional)')
    parser.add_argument('--pagespeed-strategy', default='mobile', choices=['mobile','desktop'], help='PageSpeed strategy (mobile or desktop)')
    parser.add_argument('--gsc-credentials', default=None, help='Path to GSC service account JSON (optional)')
    parser.add_argument('--gsc-property', default=None, help='GSC property URL (e.g., https://example.com/)')
    parser.add_argument('--semrush-key', default=None, help='SEMrush API key (optional)')
    parser.add_argument('--ahrefs-key', default=None, help='Ahrefs API token (optional)')
    parser.add_argument('--out', default='audit_report.json', help='Output JSON')
    parser.add_argument('--pdf-out', default='audit_report.pdf', help='Output PDF')
    args = parser.parse_args()

    auditor = AsyncWebsiteAuditor(
        base_url=args.url,
        max_pages=args.max_pages,
        timeout=args.timeout,
        user_agent=args.user_agent,
        respect_robots=args.respect_robots,
        concurrency=args.concurrency,
        pagespeed_api_key=args.pagespeed_api_key,
        pagespeed_strategy=args.pagespeed_strategy
    )

    print(f"[+] Crawling (async, concurrency={args.concurrency}) {args.url} up to {args.max_pages} pages...")
    try:
        asyncio.run(auditor.crawl())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(auditor.crawl())

    print(f"[+] Aggregating metrics and scoring...")
    report = auditor.aggregate()
    auditor.enrich_with_pagespeed(report)

    if args.gsc_property:
        gsc_client = GSCClient(args.gsc_credentials, timeout=args.timeout)
        gsc_data = gsc_client.fetch_indexed_from_sitemaps(args.gsc_property)
        report['gsc'] = gsc_data
        if gsc_data.get('indexed_pages_estimate') is not None:
            report['summary']['indexed_pages_estimate'] = gsc_data['indexed_pages_estimate']

    bk_client = BacklinksClient(args.semrush_key, args.ahrefs_key, timeout=args.timeout)
    domain = urlparse(args.url).netloc
    bk = bk_client.fetch_domain_authority(domain)
    report['backlinks'] = bk

    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[+] JSON report written to {args.out}")

    cat_chart = 'chart_categories.png'
    issues_chart = 'chart_issues.png'
    ExecutiveSummaryPDF.make_category_scores_chart(report['category_scores'], cat_chart)
    ExecutiveSummaryPDF.make_top_issues_chart(report['counts'], issues_chart)

    print(f"[+] Building executive summary PDF: {args.pdf_out}")
    pdf = ExecutiveSummaryPDF(args.pdf_out)
    pdf.add_title(report['site'], report['overall_score'], report['classification'])
    pdf.add_kpis(report['summary'], report['counts'])
    pdf.add_recommendations(report['recommendations'])
    pdf.add_chart_image(cat_chart, 'Category Scores')
    pdf.add_chart_image(issues_chart, 'Top Issues by Count')
    pdf.build()

    for p in [cat_chart, issues_chart]:
        try:
            os.remove(p)
        except Exception:
            pass

    print(f"[=] Overall Score: {report['overall_score']} — {report['classification']} ({report['summary']['good_vs_bad']})")
    print(f"[+] PDF report written to {args.pdf_out}")

if __name__ == '__main__':
    main()
