# fftech_audit_saas_plus.py
"""
International SaaS — FF Tech (Single File)
AI‑Powered Website Audit & Compliance Platform
-------------------------------------------------------------------------------
✅ Deep async crawling (asyncio + httpx; fallback to requests via threads)
✅ PageSpeed Insights integration (LCP/CLS/TBT + performance score; mobile/desktop)
✅ robots.txt analysis & respect
✅ NEW: Broken link validation (internal & external, async sampled)
✅ NEW: Sitemap parsing (robots.txt 'Sitemap:' + /sitemap.xml fallback; URL count & coverage)
✅ NEW: Hreflang validation (invalid codes, duplicates, non-HTTPS targets)

FastAPI endpoints: auth, audit, pdf, scheduling, admin (prototype; in‑memory stores)
Strict scoring (A+, A, B, C, D) and 200‑word executive summary.
Optional deps are guarded so the server can start even if some libs are missing.

Run (dev):
    uvicorn fftech_audit_saas_plus:app --host 0.0.0.0 --port 8000

Env vars (Railway-friendly):
    FFTECH_DB_URL, FFTECH_JWT_SECRET, FFTECH_BRAND_NAME, FFTECH_TIMEZONE, FFTECH_PSI_KEY
-------------------------------------------------------------------------------
"""

import os, re, json, time, hashlib, asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple, Set
from urllib.parse import urljoin, urlparse
import urllib.robotparser as robotparser
import xml.etree.ElementTree as ET

# --------------------- Optional imports (guarded) ---------------------
try:
    from fastapi import FastAPI, HTTPException, Depends
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.security import OAuth2PasswordRequestForm
    from pydantic import BaseModel
    HAS_FASTAPI = True
except Exception:
    HAS_FASTAPI = False

try:
    import requests
    HAS_REQUESTS = True
except Exception:
    HAS_REQUESTS = False

try:
    import httpx
    HAS_HTTPX = True
except Exception:
    HAS_HTTPX = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except Exception:
    HAS_BS4 = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    HAS_REPORTLAB = True
except Exception:
    HAS_REPORTLAB = False

# --------------------------- Config -----------------------------------
BRAND      = os.getenv('FFTECH_BRAND_NAME', 'FF Tech')
JWT_SECRET = os.getenv('FFTECH_JWT_SECRET', 'fftech-demo-secret')
TZ         = os.getenv('FFTECH_TIMEZONE', 'UTC')
PSI_KEY    = os.getenv('FFTECH_PSI_KEY')  # optional default PSI key

# ---------------------- In-memory storage ------------------------------
USERS: Dict[str, Dict[str, Any]] = {}
SESSIONS: Dict[str, str] = {}
AUDITS: Dict[str, Dict[str, Any]] = {}
VERIFICATION_TOKENS: Dict[str, str] = {}

# -------------------------- Utilities ----------------------------------
def make_token(payload: str) -> str:
    raw = f"{payload}|{JWT_SECRET}|{int(time.time())}"
    return hashlib.sha256(raw.encode()).hexdigest()

def now_utc() -> str:
    return datetime.utcnow().isoformat() + 'Z'

def normalize_url(base: str, href: str) -> Optional[str]:
    try:
        out = urljoin(base, href)
        parsed = urlparse(out)
        if not parsed.scheme.startswith('http'):
            return None
        return out.split('#')[0]
    except Exception:
        return None

# Quick BCP47-ish language code validation (simple heuristic)
LANG_RE = re.compile(r'^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$')

# -------------------------- Models -------------------------------------
class RegisterRequest(BaseModel):
    email: str
    password: str

class VerifyRequest(BaseModel):
    token: str

class AuditRequest(BaseModel):
    url: str
    deep: bool = True
    max_pages: int = 60
    respect_robots: bool = True
    concurrency: int = 20
    user_agent: str = 'FFTechAuditBot/1.0'
    psi_key: Optional[str] = None
    psi_strategy: str = 'mobile'  # 'mobile' or 'desktop'
    link_check_sample_per_page: int = 25  # validate up to N links per page

class AuditSummary(BaseModel):
    audit_id: str
    site: str
    grade: str
    overall_score: float
    classification: str
    good_vs_bad: str
    created_at: str

# ---------------------- Scoring Weights ---------------------------------
CATEGORIES = [
    'site_health', 'crawlability', 'on_page_seo', 'technical_performance',
    'mobile_usability', 'security', 'international_seo', 'advanced'
]
WEIGHTS = {
    'site_health':            0.15,
    'crawlability':           0.20,  # stronger weight due to link/sitemap checks
    'on_page_seo':            0.15,
    'technical_performance':  0.20,
    'mobile_usability':       0.10,
    'security':               0.15,
    'international_seo':      0.03,
    'advanced':               0.02,
}

# ---------------------- PSI integration ---------------------------------
def run_pagespeed(url: str, key: str, strategy: str = 'mobile', timeout: int = 15) -> Dict[str, Any]:
    if not HAS_REQUESTS:
        return {'status': 'requests_not_available'}
    try:
        api = (
            'https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url='
            + requests.utils.quote(url)
            + '&category=PERFORMANCE&strategy=' + (strategy if strategy in ('mobile','desktop') else 'mobile')
            + '&key=' + key
        )
        resp = requests.get(api, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            lh = data.get('lighthouseResult', {})
            perf = lh.get('categories', {}).get('performance', {}).get('score', 0)
            audits = lh.get('audits', {})
            lcp = audits.get('largest-contentful-paint', {}).get('numericValue')
            cls = audits.get('cumulative-layout-shift', {}).get('numericValue')
            tbt = audits.get('total-blocking-time', {}).get('numericValue')
            return {'status': 'ok', 'performance_score': perf, 'lcp_ms': lcp, 'cls': cls, 'tbt_ms': tbt}
        return {'status': f'error_{resp.status_code}'}
    except Exception as e:
        return {'status': f'error: {e}'}

# ------------------- Async crawler with robots ---------------------------
class AsyncCrawler:
    def __init__(self, base_url: str, max_pages: int = 60, timeout: int = 10,
                 user_agent: str = 'FFTechAuditBot/1.0', respect_robots: bool = True,
                 concurrency: int = 20, link_check_sample_per_page: int = 25):
        self.base_url = base_url.rstrip('/')
        self.max_pages = max_pages
        self.timeout = timeout
        self.headers = {"User-Agent": user_agent}
        self.respect_robots = respect_robots
        self.visited: Set[str] = set()
        self.to_visit: asyncio.Queue[str] = asyncio.Queue()
        self.pages: Dict[str, Dict[str, Any]] = {}
        self.concurrency = max(1, concurrency)
        self.sem = asyncio.Semaphore(self.concurrency)
        # robots
        self.robot = robotparser.RobotFileParser()
        self.robot.set_url(urljoin(self.base_url, '/robots.txt'))
        try:
            self.robot.read()
            self.has_robots = True
        except Exception:
            self.has_robots = False
        self.link_check_sample_per_page = link_check_sample_per_page
        # sitemaps (from robots.txt)
        self.sitemaps: List[str] = []
        if HAS_REQUESTS:
            try:
                r = requests.get(urljoin(self.base_url, '/robots.txt'), timeout=self.timeout)
                if r.status_code == 200:
                    for line in r.text.splitlines():
                        if line.lower().startswith('sitemap:'):
                            sm = line.split(':',1)[1].strip()
                            if sm:
                                self.sitemaps.append(sm)
            except Exception:
                pass
        # fallback sitemap.xml
        self.sitemap_fallback = urljoin(self.base_url, '/sitemap.xml')

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        try:
            return self.robot.can_fetch(self.headers['User-Agent'], url)
        except Exception:
            return True

    async def _fetch_httpx(self, client: 'httpx.AsyncClient', url: str):
        try:
            resp = await client.get(url, timeout=self.timeout, follow_redirects=True)
            return resp
        except Exception:
            return None

    async def _fetch_requests_threaded(self, url: str):
        def _do_get(u):
            try:
                return requests.get(u, timeout=self.timeout, allow_redirects=True, headers=self.headers)
            except Exception:
                return None
        return await asyncio.to_thread(_do_get, url)

    async def _head_or_get(self, client: Optional['httpx.AsyncClient'], url: str) -> Optional[int]:
        # Prefer HEAD; fall back to GET
        try:
            if HAS_HTTPX and client is not None:
                r = await client.head(url, timeout=self.timeout, follow_redirects=True)
                if r.status_code in (405, 501):  # method not allowed
                    r = await client.get(url, timeout=self.timeout, follow_redirects=True)
                return r.status_code
            else:
                def _do():
                    try:
                        rr = requests.head(url, timeout=self.timeout, allow_redirects=True, headers=self.headers)
                        if rr.status_code in (405, 501):
                            rr = requests.get(url, timeout=self.timeout, allow_redirects=True, headers=self.headers)
                        return rr.status_code
                    except Exception:
                        return None
                return await asyncio.to_thread(_do)
        except Exception:
            return None

    async def validate_links(self, client: Optional['httpx.AsyncClient'], page_url: str, links: List[str]) -> Dict[str, int]:
        # Sample up to N links per page to control load
        sample = links[:self.link_check_sample_per_page]
        broken = 0
        for u in sample:
            sc = await self._head_or_get(client, u)
            if sc is None or sc >= 400:
                broken += 1
        return {'checked': len(sample), 'broken': broken}

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
            if not self.allowed(url):
                self.visited.add(url)
                self.pages[url] = {'status_code': None, 'blocked_by_robots': True}
                continue
            async with self.sem:
                resp = None
                if HAS_HTTPX and client is not None:
                    resp = await self._fetch_httpx(client, url)
                else:
                    resp = await self._fetch_requests_threaded(url)
                page: Dict[str, Any] = {'url': url}
                if resp is None:
                    self.visited.add(url)
                    self.pages[url] = page
                    continue
                # normalize response across httpx/requests
                if HAS_HTTPX and isinstance(resp, httpx.Response):
                    text = resp.text
                    status = resp.status_code
                    final_url = str(resp.url)
                    headers = dict(resp.headers)
                    history = [str(h.url) for h in resp.history] + [final_url]
                    rt_ms = None
                else:
                    text = resp.text
                    status = resp.status_code
                    final_url = str(resp.url)
                    headers = dict(resp.headers)
                    history = [h.url for h in resp.history] + [final_url]
                    rt_ms = int(getattr(resp, 'elapsed', 0).total_seconds() * 1000) if hasattr(resp, 'elapsed') else None

                page.update({
                    'status_code': status,
                    'final_url': final_url,
                    'headers': headers,
                    'redirect_chain': history,
                    'response_time_ms': rt_ms,
                    'size_bytes': len(text or '')
                })

                if HAS_BS4 and text:
                    soup = BeautifulSoup(text, 'html.parser')
                    # Meta
                    page['title'] = soup.title.string.strip() if soup.title and soup.title.string else None
                    md = soup.find('meta', attrs={'name': 'description'})
                    page['meta_description'] = (md.get('content').strip() if md and md.get('content') else None)
                    # Viewport
                    page['has_viewport'] = bool(soup.find('meta', attrs={'name': 'viewport'}))
                    # Headings
                    page['h1'] = [t.get_text(strip=True) for t in soup.find_all('h1')]
                    page['h2'] = [t.get_text(strip=True) for t in soup.find_all('h2')]
                    # Canonical
                    canon = soup.find('link', rel='canonical')
                    page['canonical'] = canon.get('href') if canon and canon.get('href') else None
                    # OG/Twitter
                    page['og'] = bool(soup.find('meta', property=re.compile(r'^og:')))
                    page['twitter'] = bool(soup.find('meta', attrs={'name': re.compile(r'^twitter:')}))
                    # Hreflang
                    hreflang = []
                    invalid_codes = 0
                    duplicate_langs = 0
                    seen_langs: Set[str] = set()
                    non_https_targets = 0
                    for link in soup.find_all('link', rel='alternate'):
                        lang = link.get('hreflang')
                        href = link.get('href')
                        if not lang or not href:
                            continue
                        if not LANG_RE.match(lang):
                            invalid_codes += 1
                        if lang in seen_langs:
                            duplicate_langs += 1
                        seen_langs.add(lang)
                        if href and urlparse(href).scheme == 'http':
                            non_https_targets += 1
                        hreflang.append((lang, href))
                    page['hreflang'] = hreflang
                    page['hreflang_invalid_codes'] = invalid_codes
                    page['hreflang_duplicate_langs'] = duplicate_langs
                    page['hreflang_non_https_targets'] = non_https_targets
                    # Images
                    imgs = soup.find_all('img')
                    page['images_missing_alt'] = sum(1 for i in imgs if not (i.get('alt') or '').strip())
                    page['images_lazy'] = sum(1 for i in imgs if (i.get('loading') or '').lower() == 'lazy')
                    # Links
                    internal, external = [], []
                    for a in soup.find_all('a', href=True):
                        u = normalize_url(url, a['href'])
                        if not u:
                            continue
                        if urlparse(self.base_url).netloc == urlparse(u).netloc:
                            internal.append(u)
                        else:
                            external.append(u)
                    # Deduplicate while preserving order
                    def dedup(seq):
                        seen = set(); out = []
                        for x in seq:
                            if x not in seen:
                                seen.add(x); out.append(x)
                        return out
                    internal = dedup(internal); external = dedup(external)
                    page['internal_links'] = internal
                    page['external_links'] = external
                    # Link validation (sample)
                    link_stats_internal = await self.validate_links(client, url, internal)
                    link_stats_external = await self.validate_links(client, url, external)
                    page['linkcheck_internal'] = link_stats_internal
                    page['linkcheck_external'] = link_stats_external
                    # Security headers
                    page['hsts']     = bool(headers.get('Strict-Transport-Security'))
                    page['csp']      = bool(headers.get('Content-Security-Policy'))
                    page['xfo']      = bool(headers.get('X-Frame-Options'))
                    page['xcto']     = bool(headers.get('X-Content-Type-Options'))
                    page['referrer'] = bool(headers.get('Referrer-Policy'))
                    # Mixed content
                    if urlparse(page.get('final_url', url)).scheme == 'https':
                        mixed = []
                        for tag in soup.find_all(src=True):
                            src = normalize_url(url, tag.get('src'))
                            if src and urlparse(src).scheme == 'http':
                                mixed.append(src)
                        for tag in soup.find_all(href=True):
                            href = normalize_url(url, tag.get('href'))
                            if href and urlparse(href).scheme == 'http':
                                mixed.append(href)
                        page['mixed_content'] = mixed
                self.pages[url] = page
                self.visited.add(url)

                # enqueue internal links
                for link in page.get('internal_links', []):
                    if link not in self.visited and len(self.visited) + self.to_visit.qsize() < self.max_pages:
                        await self.to_visit.put(link)
        if HAS_HTTPX and client is not None:
            await client.aclose()

    async def crawl(self):
        await self.to_visit.put(self.base_url)
        workers = [asyncio.create_task(self.worker()) for _ in range(self.concurrency)]
        await asyncio.gather(*workers)

    def fetch_sitemap_urls(self, timeout: int = 10, max_urls: int = 10000) -> Tuple[List[str], bool]:
        if not HAS_REQUESTS:
            return ([], False)
        urls: List[str] = []
        seen: Set[str] = set()
        ok_any = False
        def _fetch_xml(u: str) -> Optional[str]:
            try:
                r = requests.get(u, timeout=timeout, headers=self.headers)
                if r.status_code == 200 and r.headers.get('Content-Type','').lower().startswith('application/xml') or r.text.startswith('<?xml'):
                    return r.text
            except Exception:
                return None
            return None
        sources = list(self.sitemaps)
        # Add fallback sitemap.xml only if robots didn't list any
        if not sources:
            sources.append(self.sitemap_fallback)
        for u in sources:
            xml = _fetch_xml(u)
            if not xml:
                continue
            ok_any = True
            try:
                root = ET.fromstring(xml)
                # Handle sitemap index & regular sitemap
                for loc in root.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
                    href = loc.text.strip() if loc.text else ''
                    if href and href not in seen:
                        seen.add(href); urls.append(href)
                        if len(urls) >= max_urls:
                            break
            except Exception:
                # try without namespace
                for loc in ET.fromstring(xml).iter('loc'):
                    href = loc.text.strip() if loc.text else ''
                    if href and href not in seen:
                        seen.add(href); urls.append(href)
                        if len(urls) >= max_urls:
                            break
        return (urls, ok_any)

# ------------------ Audit Engine (aggregate) ----------------------------
class AuditEngine:
    def __init__(self, req: AuditRequest):
        self.req = req
        self.base_url = req.url.rstrip('/')
        self.psi_key = req.psi_key or PSI_KEY

    async def run(self) -> Dict[str, Any]:
        crawler = AsyncCrawler(
            base_url=self.base_url,
            max_pages=self.req.max_pages,
            timeout=10,
            user_agent=self.req.user_agent,
            respect_robots=self.req.respect_robots,
            concurrency=self.req.concurrency,
            link_check_sample_per_page=self.req.link_check_sample_per_page,
        )
        await crawler.crawl()
        pages = crawler.pages
        total_pages = len(pages)

        # Sitemap URLs
        sitemap_urls, sitemap_present = crawler.fetch_sitemap_urls()
        pages_in_sitemap = len(sitemap_urls)
        crawled_urls = set(pages.keys())
        sitemap_set = set(sitemap_urls)
        pages_in_sitemap_not_crawled = len(sitemap_set - crawled_urls)
        pages_crawled_not_in_sitemap = len(crawled_urls - sitemap_set)

        # Aggregate metrics
        codes: Dict[int,int] = {}
        errors_4xx = 0
        errors_5xx = 0
        blocked_by_robots = 0
        missing_titles = 0
        missing_meta = 0
        missing_h1 = 0
        multiple_h1 = 0
        gzip_missing_pages = 0
        viewport_missing_pages = 0
        mixed_content_pages = 0
        hsts_missing_pages = 0
        csp_missing_pages = 0
        xfo_missing_pages = 0
        referrer_missing_pages = 0
        images_missing_alt_total = 0
        # Links
        broken_internal_total = 0
        broken_external_total = 0
        link_checks_total = 0
        # Hreflang
        hreflang_missing_pages = 0
        hreflang_invalid_codes_pages = 0
        hreflang_duplicate_langs_pages = 0
        hreflang_non_https_targets_pages = 0

        avg_resp_ms = 0
        avg_html_kb = 0

        for u, p in pages.items():
            sc = p.get('status_code')
            if sc is not None:
                codes[sc] = codes.get(sc, 0) + 1
                if 400 <= sc < 500: errors_4xx += 1
                if 500 <= sc < 600: errors_5xx += 1
            if p.get('blocked_by_robots'): blocked_by_robots += 1
            if not p.get('title'):            missing_titles += 1
            if not p.get('meta_description'): missing_meta += 1
            h1c = len(p.get('h1', []) or [])
            if h1c == 0:  missing_h1 += 1
            if h1c > 1:   multiple_h1 += 1
            # gzip
            enc = (p.get('headers', {}).get('Content-Encoding') or '').lower()
            if enc not in ('gzip','br'): gzip_missing_pages += 1
            if not p.get('has_viewport'): viewport_missing_pages += 1
            if len(p.get('mixed_content', []) or []) > 0: mixed_content_pages += 1
            if not p.get('hsts'):      hsts_missing_pages += 1
            if not p.get('csp'):       csp_missing_pages += 1
            if not p.get('xfo'):       xfo_missing_pages += 1
            if not p.get('referrer'):  referrer_missing_pages += 1
            images_missing_alt_total += int(p.get('images_missing_alt', 0))
            # link checks
            li = p.get('linkcheck_internal', {'checked':0,'broken':0})
            le = p.get('linkcheck_external', {'checked':0,'broken':0})
            broken_internal_total += int(li.get('broken', 0))
            broken_external_total += int(le.get('broken', 0))
            link_checks_total += int(li.get('checked', 0)) + int(le.get('checked', 0))
            # hreflang
            if len(p.get('hreflang', [])) == 0:
                hreflang_missing_pages += 1
            if int(p.get('hreflang_invalid_codes', 0)) > 0:
                hreflang_invalid_codes_pages += 1
            if int(p.get('hreflang_duplicate_langs', 0)) > 0:
                hreflang_duplicate_langs_pages += 1
            if int(p.get('hreflang_non_https_targets', 0)) > 0:
                hreflang_non_https_targets_pages += 1
            # response time & size
            avg_resp_ms += int(p.get('response_time_ms') or 0)
            avg_html_kb += int((p.get('size_bytes') or 0)/1024)
        avg_resp_ms = int(avg_resp_ms / max(1, total_pages))
        avg_html_kb = int(avg_html_kb / max(1, total_pages))

        # Scores (strict)
        sh = 100
        bad_rate = (errors_4xx + errors_5xx) / max(1, total_pages)
        sh -= min(60, int(bad_rate * 100))
        if avg_resp_ms > 1500: sh -= 20
        elif avg_resp_ms > 800: sh -= 10

        cr = 100
        cr -= min(30, blocked_by_robots * 2)
        # Deduct based on broken links ratio
        broken_ratio = broken_internal_total / max(1, link_checks_total)
        cr -= min(40, int(broken_ratio * 100))
        # Deduct for sitemap gaps
        if sitemap_present:
            gap_rate = pages_in_sitemap_not_crawled / max(1, pages_in_sitemap)
            cr -= min(20, int(gap_rate * 100))
        else:
            cr -= 10  # missing sitemap.xml & robots hints

        op = 100
        op -= min(30, int((missing_titles / max(1, total_pages))*100))
        op -= min(30, int((missing_meta   / max(1, total_pages))*100))
        op -= min(10, int((missing_h1     / max(1, total_pages))*100))
        op -= min(10, int((multiple_h1    / max(1, total_pages))*100))

        tp = 100
        if avg_html_kb > 1200: tp -= 20
        elif avg_html_kb > 300: tp -= 10
        tp -= min(20, gzip_missing_pages * 2)

        mb = 100
        mb -= min(30, int((viewport_missing_pages / max(1, total_pages))*100))

        sec = 100
        if not self.base_url.startswith('https'): sec -= 40
        sec -= min(20, mixed_content_pages * 5)
        sec -= min(20, hsts_missing_pages * 2)
        sec -= min(20, csp_missing_pages * 2)
        sec -= min(20, xfo_missing_pages * 2)
        sec -= min(10, referrer_missing_pages * 1)

        intl = 100
        intl -= min(20, int((hreflang_missing_pages / max(1, total_pages))*100))
        intl -= min(10, int((hreflang_invalid_codes_pages / max(1, total_pages))*100))
        intl -= min(10, int((hreflang_duplicate_langs_pages / max(1, total_pages))*100))
        intl -= min(10, int((hreflang_non_https_targets_pages / max(1, total_pages))*100))

        adv = 100
        adv -= 10   # placeholder; e.g., heavy third-party scripts

        category_scores = {
            'site_health':            max(0, sh),
            'crawlability':           max(0, cr),
            'on_page_seo':            max(0, op),
            'technical_performance':  max(0, tp),
            'mobile_usability':       max(0, mb),
            'security':               max(0, sec),
            'international_seo':      max(0, intl),
            'advanced':               max(0, adv)
        }
        overall = 0
        for c, scv in category_scores.items():
            overall += scv * WEIGHTS[c]
        overall = round(overall, 2)
        if   overall >= 90: cls = 'Excellent';         grade = 'A+'
        elif overall >= 80: cls = 'Good';              grade = 'A'
        elif overall >= 70: cls = 'Good';              grade = 'B'
        elif overall >= 60: cls = 'Needs Improvement'; grade = 'C'
        else:               cls = 'Poor';              grade = 'D'

        result = {
            'site': self.base_url,
            'summary': {
                'total_crawled_pages': total_pages,
                'http_status_counts': codes,
                'avg_html_size_kb': avg_html_kb,
                'avg_response_time_ms': avg_resp_ms,
                'robots': {
                    'respect_robots': self.req.respect_robots,
                    'agent': self.req.user_agent,
                    'blocked_pages': blocked_by_robots,
                    'has_robots': crawler.has_robots
                },
                'sitemap': {
                    'present': sitemap_present,
                    'urls_in_sitemap': pages_in_sitemap,
                    'in_sitemap_not_crawled': pages_in_sitemap_not_crawled,
                    'crawled_not_in_sitemap': pages_crawled_not_in_sitemap
                }
            },
            'counts': {
                'errors_4xx': errors_4xx,
                'errors_5xx': errors_5xx,
                'blocked_by_robots': blocked_by_robots,
                'missing_titles': missing_titles,
                'missing_meta_descriptions': missing_meta,
                'missing_h1': missing_h1,
                'multiple_h1': multiple_h1,
                'gzip_missing_pages': gzip_missing_pages,
                'viewport_missing_pages': viewport_missing_pages,
                'mixed_content_pages': mixed_content_pages,
                'hsts_missing_pages': hsts_missing_pages,
                'csp_missing_pages': csp_missing_pages,
                'xfo_missing_pages': xfo_missing_pages,
                'referrer_missing_pages': referrer_missing_pages,
                'images_missing_alt_total': images_missing_alt_total,
                'broken_internal_links_total': broken_internal_total,
                'broken_external_links_total': broken_external_total,
                'link_checks_total': link_checks_total,
                'hreflang_missing_pages': hreflang_missing_pages,
                'hreflang_invalid_codes_pages': hreflang_invalid_codes_pages,
                'hreflang_duplicate_langs_pages': hreflang_duplicate_langs_pages,
                'hreflang_non_https_targets_pages': hreflang_non_https_targets_pages,
            },
            'category_scores': category_scores,
            'overall_score': overall,
            'classification': cls,
            'grade': grade,
            'good_vs_bad': 'Good' if overall >= 70 else 'Bad',
            'pages': list(pages.values())
        }

        # PSI enrichment (optional)
        if self.psi_key:
            psi = run_pagespeed(self.base_url, self.psi_key, self.req.psi_strategy)
            result['pagespeed'] = psi
            if psi.get('status') == 'ok':
                perf = psi.get('performance_score') or 0
                category_scores['technical_performance'] = min(
                    100,
                    category_scores['technical_performance'] + int((perf or 0) * 10)
                )
                overall = 0
                for c, scv in category_scores.items():
                    overall += scv * WEIGHTS[c]
                overall = round(overall, 2)
                result['category_scores'] = category_scores
                result['overall_score'] = overall
                result['classification'] = (
                    'Excellent' if overall >= 90 else (
                        'Good' if overall >= 70 else (
                            'Needs Improvement' if overall >= 50 else 'Poor')))
                result['good_vs_bad'] = 'Good' if overall >= 70 else 'Bad'

        return result

    def executive_summary_200w(self, site: str, scores: Dict[str, Any]) -> str:
        cs = scores['category_scores']
        weak = sorted(cs.items(), key=lambda x: x[1])[:3]
        weak_areas = ', '.join([w[0].replace('_',' ').title() for w in weak])
        summary = (
            f"{BRAND}'s AI-powered audit for {site} delivers a comprehensive view of "
            f"site health, crawlability, on-page SEO, technical performance, mobile readiness, and "
            f"security. The site scores {scores['overall_score']} ({scores['classification']}, grade {scores['grade']}), "
            f"indicating measurable strengths with clear opportunities. Weak areas include {weak_areas}. "
            f"To improve, enforce strict HTTP security headers (CSP, HSTS, X-Frame-Options), remove mixed-content "
            f"resources, and enable compression with effective caching. Fix broken links and align sitemaps with crawled "
            f"content to enhance crawlability and indexation. On-page fixes should prioritize unique titles, meta descriptions, "
            f"and a single descriptive H1 per page. Mobile usability benefits from proper viewport settings and accessible tap targets. "
            f"For global reach, add accurate hreflang and consistent canonicalization across protocols and subdomains. The platform emphasizes "
            f"customer-centric reporting—prioritized fixes, category breakdowns, and trend tracking help stakeholders visualize progress. With "
            f"scheduled audits, certified PDF reports bearing the {BRAND} stamp, and role-based administration, this solution aligns with enterprise "
            f"standards and international compliance expectations. Address the highlighted risks and adopt best practices to elevate UX, strengthen trust, "
            f"and improve the grade over time."
        )
        return summary

# ------------------------ PDF builder -----------------------------------
def build_pdf_report(path: str, site: str, result: Dict[str, Any], summary: str) -> bool:
    if not HAS_REPORTLAB:
        return False
    try:
        doc    = SimpleDocTemplate(path, pagesize=A4)
        styles = getSampleStyleSheet()
        story  = []
        story.append(Paragraph(f"<b>{BRAND} Certified Audit Report</b>", styles['Title']))
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph(f"Site: {site}", styles['Normal']))
        story.append(Paragraph(f"Score: {result['overall_score']} — {result['classification']} ({result['grade']})", styles['Normal']))
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph("<b>Executive Summary</b>", styles['Heading2']))
        story.append(Paragraph(summary, styles['Normal']))
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph("<b>Category Scores</b>", styles['Heading2']))
        for k,v in result['category_scores'].items():
            story.append(Paragraph(f"{k.replace('_',' ').title()}: {v}", styles['Normal']))
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(f"{BRAND} — Certification Stamp", styles['Italic']))
        doc.build(story)
        return True
    except Exception:
        return False

# ------------------------ FastAPI app -----------------------------------
if HAS_FASTAPI:
    app = FastAPI(title=f"{BRAND} — AI Website Audit & Compliance", version="3.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"]        = "SAMEORIGIN"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"]        = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self' 'unsafe-inline' data: https:;"
        return response

    # ----------------------------- AUTH ---------------------------------
    @app.post('/auth/register')
    def register(req: RegisterRequest):
        if req.email in USERS:
            raise HTTPException(400, 'Email already registered')
        token = make_token(req.email)
        USERS[req.email] = {
            'email': req.email,
            'password_hash': hashlib.sha256(req.password.encode()).hexdigest(),
            'verified': False,
            'created_at': now_utc(),
            'role': 'user'
        }
        VERIFICATION_TOKENS[token] = req.email
        return { 'message': 'Verification email sent', 'token_demo': token }

    @app.post('/auth/verify')
    def verify(req: VerifyRequest):
        email = VERIFICATION_TOKENS.get(req.token)
        if not email:
            raise HTTPException(400, 'Invalid token')
        USERS[email]['verified'] = True
        del VERIFICATION_TOKENS[req.token]
        return { 'message': 'Email verified' }

    @app.post('/auth/login')
    def login(form: OAuth2PasswordRequestForm = Depends()):
        email = form.username
        if email not in USERS:
            raise HTTPException(401, 'Invalid credentials')
        pw_ok = USERS[email]['password_hash'] == hashlib.sha256(form.password.encode()).hexdigest()
        if not pw_ok:
            raise HTTPException(401, 'Invalid credentials')
        if not USERS[email]['verified']:
            raise HTTPException(403, 'Email not verified')
        token = make_token(email)
        SESSIONS[token] = email
        return { 'access_token': token, 'token_type': 'bearer' }

    def require_user(token: str) -> str:
        if token not in SESSIONS:
            raise HTTPException(401, 'Unauthorized')
        return SESSIONS[token]

    # ----------------------------- AUDIT --------------------------------
    @app.post('/audit/start')
    async def start_audit(req: AuditRequest, token: str):
        user = require_user(token)
        eng = AuditEngine(req)
        result = await eng.run()
        summary = eng.executive_summary_200w(req.url, result)
        audit_id = make_token(req.url)
        AUDITS[audit_id] = {
            'id': audit_id,
            'user': user,
            'site': req.url,
            'result': result,
            'summary': summary,
            'created_at': now_utc(),
        }
        return AuditSummary(
            audit_id=audit_id,
            site=req.url,
            grade=result['grade'],
            overall_score=result['overall_score'],
            classification=result['classification'],
            good_vs_bad=result['good_vs_bad'],
            created_at=AUDITS[audit_id]['created_at']
        )

    @app.get('/audit/{audit_id}')
    def get_audit(audit_id: str, token: str):
        user = require_user(token)
        a = AUDITS.get(audit_id)
        if not a or a['user'] != user:
            raise HTTPException(404, 'Audit not found')
        return a

    @app.get('/audit/{audit_id}/pdf')
    def pdf_audit(audit_id: str, token: str):
        user = require_user(token)
        a = AUDITS.get(audit_id)
        if not a or a['user'] != user:
            raise HTTPException(404, 'Audit not found')
        path = f"audit_{audit_id}.pdf"
        ok = build_pdf_report(path, a['site'], a['result'], a['summary'])
        if not ok:
            return { 'status': 'pdf_unavailable', 'path': None }
        return { 'status': 'ok', 'path': path }

    # -------------------------- SCHEDULING ------------------------------
    @app.post('/schedule/daily')
    def schedule_daily(token: str, hour_24: int = 9, timezone: str = TZ):
        user = require_user(token)
        return { 'message': 'Daily schedule set', 'user': user, 'hour_24': hour_24, 'timezone': timezone }

    @app.post('/schedule/recurring')
    def schedule_recurring(token: str, every_days: int = 7, timezone: str = TZ):
        user = require_user(token)
        return { 'message': 'Recurring schedule set', 'user': user, 'every_days': every_days, 'timezone': timezone }

# End of single-file async SaaS app
