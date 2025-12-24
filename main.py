#!/usr/bin/env python3
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
import os
import re
import json
import time
import hashlib
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple, Set
from urllib.parse import urljoin, urlparse, quote

import urllib.robotparser as robotparser
import xml.etree.ElementTree as ET

# --------------------- Optional imports (guarded) ---------------------
try:
    from fastapi import FastAPI, HTTPException, Depends, Request
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
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    HAS_REPORTLAB = True
except Exception:
    HAS_REPORTLAB = False

# --------------------------- Config -----------------------------------
BRAND = os.getenv('FFTECH_BRAND_NAME', 'FF Tech')
JWT_SECRET = os.getenv('FFTECH_JWT_SECRET', 'fftech-demo-secret')
TZ = os.getenv('FFTECH_TIMEZONE', 'UTC')
PSI_KEY = os.getenv('FFTECH_PSI_KEY')

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

LANG_RE = re.compile(r'^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$')

# -------------------------- Models -------------------------------------
if HAS_FASTAPI:
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
        psi_strategy: str = 'mobile'
        link_check_sample_per_page: int = 25

    class AuditSummary(BaseModel):
        audit_id: str
        site: str
        grade: str
        overall_score: float
        classification: str
        good_vs_bad: str
        created_at: str

# ---------------------- Scoring Weights ---------------------------------
WEIGHTS = {
    'site_health': 0.15,
    'crawlability': 0.20,
    'on_page_seo': 0.15,
    'technical_performance': 0.20,
    'mobile_usability': 0.10,
    'security': 0.15,
    'international_seo': 0.03,
    'advanced': 0.02,
}

# ---------------------- PSI integration ---------------------------------
def run_pagespeed(url: str, key: str, strategy: str = 'mobile', timeout: int = 15) -> Dict[str, Any]:
    if not HAS_REQUESTS:
        return {'status': 'requests_not_available'}
    try:
        api = (
            'https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url='
            + quote(url)
            + '&category=PERFORMANCE&strategy=' + (strategy if strategy in ('mobile', 'desktop') else 'mobile')
            + '&key=' + key
        )
        resp = requests.get(api, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            lh = data.get('lighthouseResult', {})
            perf = lh.get('categories', {}).get('performance', {}).get('score', 0) * 100  # to 0-100
            audits = lh.get('audits', {})
            lcp = audits.get('largest-contentful-paint', {}).get('numericValue')
            cls = audits.get('cumulative-layout-shift', {}).get('numericValue')
            tbt = audits.get('total-blocking-time', {}).get('numericValue')
            return {'status': 'ok', 'performance_score': perf, 'lcp_ms': lcp, 'cls': cls, 'tbt_ms': tbt}
        return {'status': f'error_{resp.status_code}'}
    except Exception as e:
        return {'status': f'error: {str(e)}'}

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
        self.link_check_sample_per_page = link_check_sample_per_page

        # robots.txt
        self.robot = None
        self.has_robots = False
        if respect_robots and HAS_REQUESTS:
            try:
                rp = robotparser.RobotFileParser()
                rp.set_url(urljoin(self.base_url, '/robots.txt'))
                rp.read()
                self.robot = rp
                self.has_robots = True
            except Exception:
                pass

        # sitemaps from robots.txt
        self.sitemaps: List[str] = []
        if HAS_REQUESTS:
            try:
                r = requests.get(urljoin(self.base_url, '/robots.txt'), timeout=timeout)
                if r.status_code == 200:
                    for line in r.text.splitlines():
                        if line.lower().startswith('sitemap:'):
                            sm = line.split(':', 1)[1].strip()
                            if sm:
                                self.sitemaps.append(sm)
            except Exception:
                pass

        self.sitemap_fallback = urljoin(self.base_url, '/sitemap.xml')

    def allowed(self, url: str) -> bool:
        if not self.respect_robots or self.robot is None:
            return True
        try:
            return self.robot.can_fetch(self.headers['User-Agent'], url)
        except Exception:
            return True

    async def _fetch_httpx(self, client: httpx.AsyncClient, url: str):
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

    async def _head_or_get(self, client: Optional[httpx.AsyncClient], url: str) -> Optional[int]:
        try:
            if HAS_HTTPX and client is not None:
                r = await client.head(url, timeout=self.timeout, follow_redirects=True)
                if r.status_code in (405, 501):
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

    async def validate_links(self, client: Optional[httpx.AsyncClient], links: List[str]) -> Dict[str, int]:
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
            client = httpx.AsyncClient(headers=self.headers, timeout=self.timeout)

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

                # Unified response handling
                if HAS_HTTPX and isinstance(resp, httpx.Response):
                    text = resp.text
                    status = resp.status_code
                    final_url = str(resp.url)
                    headers = dict(resp.headers)
                    history = [str(h.url) for h in resp.history] + [final_url]
                else:
                    text = resp.text
                    status = resp.status_code
                    final_url = str(resp.url)
                    headers = dict(resp.headers)
                    history = [str(h.url) for h in resp.history] + [final_url]

                page.update({
                    'status_code': status,
                    'final_url': final_url,
                    'headers': headers,
                    'redirect_chain': history,
                    'size_bytes': len(text or '')
                })

                if HAS_BS4 and text:
                    soup = BeautifulSoup(text, 'html.parser')
                    page['title'] = soup.title.string.strip() if soup.title and soup.title.string else None
                    md = soup.find('meta', attrs={'name': 'description'})
                    page['meta_description'] = md.get('content').strip() if md and md.get('content') else None
                    page['has_viewport'] = bool(soup.find('meta', attrs={'name': 'viewport'}))
                    page['h1'] = [t.get_text(strip=True) for t in soup.find_all('h1')]

                    canon = soup.find('link', rel=lambda v: v and 'canonical' in str(v).lower() if v else False)
                    page['canonical'] = canon.get('href') if canon else None

                    page['og'] = bool(soup.find('meta', property=re.compile(r'^og:')))
                    page['twitter'] = bool(soup.find('meta', attrs={'name': re.compile(r'^twitter:')}))

                    hreflang = []
                    invalid_codes = duplicate_langs = non_https_targets = 0
                    seen = set()
                    for link in soup.find_all('link', rel=lambda v: v and 'alternate' in str(v).lower() if v else False):
                        lang = link.get('hreflang')
                        href = link.get('href')
                        if lang and href:
                            if not LANG_RE.match(lang):
                                invalid_codes += 1
                            if lang in seen:
                                duplicate_langs += 1
                            seen.add(lang)
                            if urlparse(href).scheme == 'http':
                                non_https_targets += 1
                            hreflang.append((lang, href))
                    page['hreflang'] = hreflang
                    page['hreflang_invalid_codes'] = invalid_codes
                    page['hreflang_duplicate_langs'] = duplicate_langs
                    page['hreflang_non_https_targets'] = non_https_targets

                    imgs = soup.find_all('img')
                    page['images_missing_alt'] = sum(1 for i in imgs if not i.get('alt') or not i.get('alt').strip())
                    page['images_lazy'] = sum(1 for i in imgs if i.get('loading') == 'lazy')

                    internal = []
                    external = []
                    for a in soup.find_all('a', href=True):
                        u = normalize_url(url, a['href'])
                        if u:
                            if is_same_domain(self.base_url, u):
                                internal.append(u)
                            else:
                                external.append(u)

                    # Dedup preserving order
                    def dedup(seq):
                        seen = set()
                        return [x for x in seq if not (x in seen or seen.add(x))]
                    page['internal_links'] = dedup(internal)
                    page['external_links'] = dedup(external)

                    int_check = await self.validate_links(client, internal)
                    ext_check = await self.validate_links(client, external)
                    page['linkcheck_internal'] = int_check
                    page['linkcheck_external'] = ext_check

                    page['hsts'] = bool(headers.get('Strict-Transport-Security'))
                    page['csp'] = bool(headers.get('Content-Security-Policy'))
                    page['xfo'] = bool(headers.get('X-Frame-Options'))
                    page['xcto'] = bool(headers.get('X-Content-Type-Options'))
                    page['referrer'] = bool(headers.get('Referrer-Policy'))

                    if urlparse(final_url).scheme == 'https':
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

                for link in page.get('internal_links', []):
                    if link not in self.visited and len(self.visited) + self.to_visit.qsize() < self.max_pages:
                        await self.to_visit.put(link)

        if HAS_HTTPX and client is not None:
            await client.aclose()

    async def crawl(self):
        await self.to_visit.put(self.base_url)
        tasks = [asyncio.create_task(self.worker()) for _ in range(self.concurrency)]
        await asyncio.gather(*tasks)

    def fetch_sitemap_urls(self, timeout: int = 10, max_urls: int = 10000) -> Tuple[List[str], bool]:
        if not HAS_REQUESTS:
            return [], False
        urls = []
        seen = set()
        ok_any = False
        sources = self.sitemaps[:] or [self.sitemap_fallback]
        for u in sources:
            try:
                r = requests.get(u, timeout=timeout, headers=self.headers)
                if r.status_code != 200:
                    continue
                xml = r.text
                ok_any = True
                root = ET.fromstring(xml)
                for loc in root.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
                    href = loc.text.strip() if loc.text else ''
                    if href and href not in seen:
                        seen.add(href)
                        urls.append(href)
                        if len(urls) >= max_urls:
                            return urls, ok_any
            except Exception:
                continue
        return urls, ok_any

# ------------------ Audit Engine (aggregate) ----------------------------
class AuditEngine:
    def __init__(self, req: 'AuditRequest'):
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
        total_pages = len(pages) or 1

        sitemap_urls, sitemap_present = crawler.fetch_sitemap_urls()
        sitemap_set = set(sitemap_urls)
        crawled_set = set(pages.keys())
        in_sitemap_not_crawled = len(sitemap_set - crawled_set)
        crawled_not_in_sitemap = len(crawled_set - sitemap_set)

        # Aggregation (fixed divisions, safe defaults)
        codes = {}
        errors_4xx = errors_5xx = blocked_by_robots = 0
        missing_titles = missing_meta = missing_h1 = multiple_h1 = 0
        gzip_missing_pages = viewport_missing_pages = mixed_content_pages = 0
        hsts_missing_pages = csp_missing_pages = xfo_missing_pages = referrer_missing_pages = 0
        images_missing_alt_total = broken_internal_total = broken_external_total = link_checks_total = 0
        hreflang_missing_pages = hreflang_invalid_codes_pages = hreflang_duplicate_langs_pages = hreflang_non_https_targets_pages = 0
        avg_resp_ms = avg_html_kb = 0

        for p in pages.values():
            sc = p.get('status_code')
            if sc is not None:
                codes[sc] = codes.get(sc, 0) + 1
                if 400 <= sc < 500: errors_4xx += 1
                if 500 <= sc < 600: errors_5xx += 1
            if p.get('blocked_by_robots'): blocked_by_robots += 1
            if not p.get('title'): missing_titles += 1
            if not p.get('meta_description'): missing_meta += 1
            h1c = len(p.get('h1', []))
            if h1c == 0: missing_h1 += 1
            if h1c > 1: multiple_h1 += 1
            if (p.get('headers', {}).get('Content-Encoding') or '').lower() not in ('gzip', 'br'):
                gzip_missing_pages += 1
            if not p.get('has_viewport'): viewport_missing_pages += 1
            if p.get('mixed_content'): mixed_content_pages += 1
            if not p.get('hsts'): hsts_missing_pages += 1
            if not p.get('csp'): csp_missing_pages += 1
            if not p.get('xfo'): xfo_missing_pages += 1
            if not p.get('referrer'): referrer_missing_pages += 1
            images_missing_alt_total += p.get('images_missing_alt', 0)
            li = p.get('linkcheck_internal', {})
            le = p.get('linkcheck_external', {})
            broken_internal_total += li.get('broken', 0)
            broken_external_total += le.get('broken', 0)
            link_checks_total += li.get('checked', 0) + le.get('checked', 0)
            if len(p.get('hreflang', [])) == 0: hreflang_missing_pages += 1
            if p.get('hreflang_invalid_codes', 0) > 0: hreflang_invalid_codes_pages += 1
            if p.get('hreflang_duplicate_langs', 0) > 0: hreflang_duplicate_langs_pages += 1
            if p.get('hreflang_non_https_targets', 0) > 0: hreflang_non_https_targets_pages += 1
            avg_resp_ms += p.get('response_time_ms', 0)
            avg_html_kb += (p.get('size_bytes', 0) // 1024)

        avg_resp_ms = avg_resp_ms // total_pages
        avg_html_kb = avg_html_kb // total_pages

        # Scoring (safe, percentage-based)
        category_scores = {}
        sh = 100 - min(60, int((errors_4xx + errors_5xx) / total_pages * 100))
        sh -= 20 if avg_resp_ms > 1500 else (10 if avg_resp_ms > 800 else 0)
        category_scores['site_health'] = max(0, sh)

        cr = 100 - min(30, blocked_by_robots * 2)
        broken_ratio = broken_internal_total / max(1, link_checks_total)
        cr -= min(40, int(broken_ratio * 100))
        if sitemap_present:
            gap = in_sitemap_not_crawled / max(1, len(sitemap_urls))
            cr -= min(20, int(gap * 100))
        else:
            cr -= 10
        category_scores['crawlability'] = max(0, cr)

        op = 100
        op -= min(30, int(missing_titles / total_pages * 100))
        op -= min(30, int(missing_meta / total_pages * 100))
        op -= min(10, int(missing_h1 / total_pages * 100))
        op -= min(10, int(multiple_h1 / total_pages * 100))
        category_scores['on_page_seo'] = max(0, op)

        tp = 100
        if avg_html_kb > 1200: tp -= 20
        elif avg_html_kb > 300: tp -= 10
        tp -= min(20, gzip_missing_pages * 2)
        category_scores['technical_performance'] = max(0, tp)

        mb = 100 - min(30, int(viewport_missing_pages / total_pages * 100))
        category_scores['mobile_usability'] = max(0, mb)

        sec = 100
        if not self.base_url.startswith('https'): sec -= 40
        sec -= min(20, mixed_content_pages * 5)
        sec -= min(20, hsts_missing_pages * 2)
        sec -= min(20, csp_missing_pages * 2)
        sec -= min(20, xfo_missing_pages * 2)
        sec -= min(10, referrer_missing_pages)
        category_scores['security'] = max(0, sec)

        intl = 100
        intl -= min(20, int(hreflang_missing_pages / total_pages * 100))
        intl -= min(10, int(hreflang_invalid_codes_pages / total_pages * 100))
        intl -= min(10, int(hreflang_duplicate_langs_pages / total_pages * 100))
        intl -= min(10, int(hreflang_non_https_targets_pages / total_pages * 100))
        category_scores['international_seo'] = max(0, intl)

        category_scores['advanced'] = 100  # placeholder

        overall = sum(category_scores[c] * WEIGHTS[c] for c in WEIGHTS)
        overall = round(overall, 2)

        grade = 'A+' if overall >= 90 else 'A' if overall >= 80 else 'B' if overall >= 70 else 'C' if overall >= 60 else 'D'
        classification = 'Excellent' if overall >= 90 else 'Good' if overall >= 70 else 'Needs Improvement' if overall >= 50 else 'Poor'

        result = {
            'site': self.base_url,
            'summary': {
                'total_crawled_pages': total_pages,
                'http_status_counts': codes,
                'avg_html_size_kb': avg_html_kb,
                'avg_response_time_ms': avg_resp_ms,
                'robots': {'blocked_pages': blocked_by_robots, 'has_robots': crawler.has_robots},
                'sitemap': {
                    'present': sitemap_present,
                    'urls_in_sitemap': len(sitemap_urls),
                    'in_sitemap_not_crawled': in_sitemap_not_crawled,
                    'crawled_not_in_sitemap': crawled_not_in_sitemap
                }
            },
            'counts': {
                'errors_4xx': errors_4xx,
                'errors_5xx': errors_5xx,
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
            'classification': classification,
            'grade': grade,
            'good_vs_bad': 'Good' if overall >= 70 else 'Bad',
            'pages': list(pages.values())
        }

        if self.psi_key:
            psi = run_pagespeed(self.base_url, self.psi_key, self.req.psi_strategy)
            result['pagespeed'] = psi
            if psi.get('status') == 'ok':
                perf = psi.get('performance_score', 0)
                category_scores['technical_performance'] = min(100, category_scores['technical_performance'] + perf // 10)
                overall = sum(category_scores[c] * WEIGHTS[c] for c in WEIGHTS)
                overall = round(overall, 2)
                result['overall_score'] = overall
                result['classification'] = 'Excellent' if overall >= 90 else 'Good' if overall >= 70 else 'Needs Improvement' if overall >= 50 else 'Poor'
                result['good_vs_bad'] = 'Good' if overall >= 70 else 'Bad'

        return result

    def executive_summary_200w(self, site: str, result: Dict[str, Any]) -> str:
        cs = result['category_scores']
        weak = ', '.join(sorted(cs, key=cs.get)[:3])
        return (
            f"{BRAND} audit of {site} reveals an overall score of {result['overall_score']} ({result['classification']}, grade {result['grade']}). "
            f"Weakest categories: {weak}. Key recommendations: enforce HTTPS with HSTS, eliminate mixed content, implement CSP/X-Frame-Options, "
            f"enable compression, optimize render-blocking resources, ensure viewport meta tag, fix broken links, align sitemap coverage, "
            f"use unique titles/meta descriptions, single H1, and valid hreflang tags. This improves crawlability, security, performance, and global reach."
        )

# ------------------------ PDF builder -----------------------------------
def build_pdf_report(path: str, site: str, result: Dict[str, Any], summary: str) -> bool:
    if not HAS_REPORTLAB:
        return False
    try:
        doc = SimpleDocTemplate(path, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        story.append(Paragraph(f"<b>{BRAND} Certified Audit Report</b>", styles['Title']))
        story.append(Spacer(1, cm))
        story.append(Paragraph(f"Site: {site}", styles['Normal']))
        story.append(Paragraph(f"Score: {result['overall_score']} — {result['classification']} ({result['grade']})", styles['Normal']))
        story.append(Spacer(1, cm))
        story.append(Paragraph("<b>Executive Summary</b>", styles['Heading2']))
        story.append(Paragraph(summary, styles['Normal']))
        story.append(Spacer(1, cm))
        story.append(Paragraph("<b>Category Scores</b>", styles['Heading2']))
        for k, v in result['category_scores'].items():
            story.append(Paragraph(f"{k.replace('_', ' ').title()}: {v}", styles['Normal']))
        doc.build(st
