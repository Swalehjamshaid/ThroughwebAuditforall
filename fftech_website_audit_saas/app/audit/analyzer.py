from typing import Dict, Any, List
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup
from .crawler import simple_crawl  # Assume this returns CrawlResult object
from ..config import settings
import time
import re
from concurrent.futures import ThreadPoolExecutor  # For parallel API calls

# Helper: Safe API call for PageSpeed (Core Web Vitals + performance metrics)
def _pagespeed_insights(url: str, strategy: str = 'desktop') -> Dict[str, Any]:
    if not settings.GOOGLE_PSI_API_KEY:
        return {'score': 70, 'LCP': 70, 'FCP': 70, 'CLS': 70, 'TBT': 70, 'SpeedIndex': 70}
    try:
        api = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
        params = {
            'url': url,
            'key': settings.GOOGLE_PSI_API_KEY,
            'category': ['performance', 'seo', 'accessibility'],
            'strategy': strategy
        }
        r = requests.get(api, params=params, timeout=30)
        if r.status_code != 200:
            return {'score': 50, 'LCP': 50, 'FCP': 50, 'CLS': 50, 'TBT': 50, 'SpeedIndex': 50}

        data = r.json()
        lh = data.get('lighthouseResult', {})
        audits = lh.get('audits', {})
        categories = lh.get('categories', {})

        def get_score(val, good, poor):
            if val is None:
                return 50
            val = float(val) if isinstance(val, (str, int, float)) else 0
            if val <= good:
                return 100
            if val >= poor:
                return 0
            return round(100 * (poor - val) / (poor - good), 2)

        return {
            'overall_performance': categories.get('performance', {}).get('score', 0) * 100,
            'LCP': get_score(audits.get('largest-contentful-paint', {}).get('numericValue'), 2500, 4000),
            'FCP': get_score(audits.get('first-contentful-paint', {}).get('numericValue'), 1800, 3000),
            'CLS': get_score(audits.get('cumulative-layout-shift', {}).get('numericValue'), 0.1, 0.25),
            'TBT': get_score(audits.get('total-blocking-time', {}).get('numericValue'), 200, 600),
            'SpeedIndex': get_score(audits.get('speed-index', {}).get('numericValue'), 3400, 5800),
            'TTI': get_score(audits.get('interactive', {}).get('numericValue'), 3800, 7300),
            'FID': get_score(audits.get('max-potential-fid', {}).get('numericValue'), 100, 300),
            'total_page_size': audits.get('total-byte-weight', {}).get('numericValue', 0) / 1024 / 1024,  # MB
            'requests_per_page': len(audits.get('network-requests', {}).get('details', {}).get('items', [])),
            'unminified_css': audits.get('unminified-css', {}).get('score', 1) * 100,
            'unminified_js': audits.get('unminified-javascript', {}).get('score', 1) * 100,
            'render_blocking': audits.get('render-blocking-resources', {}).get('score', 1) * 100,
            'dom_size': audits.get('dom-size', {}).get('numericValue', 0),
            'third_party_load': audits.get('third-party-summary', {}).get('score', 1) * 100,
            'server_response_time': audits.get('server-response-time', {}).get('numericValue', 0),
            'image_optimization': audits.get('uses-optimized-images', {}).get('score', 1) * 100,
            'lazy_loading': audits.get('uses-lazy-loading', {}).get('score', 1) * 100,
            'caching': audits.get('uses-long-cache-ttl', {}).get('score', 1) * 100,
            'compression': audits.get('uses-text-compression', {}).get('score', 1) * 100
        }
    except Exception:
        return {'overall_performance': 60}  # fallback

# Helper: Mobile-specific check
def _mobile_friendly_test(url: str) -> Dict[str, float]:
    try:
        api = "https://searchconsole.googleapis.com/v1/urlTestingTools/mobileFriendlyTest:run"
        params = {'url': url, 'key': settings.GOOGLE_PSI_API_KEY}
        r = requests.post(api, params=params, timeout=20)
        data = r.json()
        return {
            'mobile_friendly': 100 if data.get('mobileFriendlyIssues') is None else 20,
            'viewport': 100 if 'viewport' not in data.get('mobileFriendlyIssues', []) else 0,
            # Add more from spec 98–104
        }
    except:
        return {'mobile_friendly': 50}

# Helper: Backlinks/DA placeholder (use Moz API or free alternative)
def _get_backlinks_info(url: str) -> Dict[str, Any]:
    # Placeholder – integrate Moz API key for real data
    return {
        'domain_authority': 45,  # mock
        'total_backlinks': 1200,
        'toxic_backlinks': 50,
        # Expand for 118–125
    }

# Main analyze function
def analyze(url: str, competitors: List[str] = None) -> Dict[str, Any]:
    results = {}

    # A. Executive Summary (1–10) – calculated later

    # B. Overall Site Health (11–20)
    crawl = simple_crawl(url)
    pages = crawl.pages
    total_pages = len(pages)
    errors = crawl.errors
    warnings = len([e for e in errors if 'warning' in e.lower()])
    notices = len([e for e in errors if 'notice' in e.lower()])
    indexed_pages = total_pages - len([p for p in pages if p.get('noindex', False)])
    orphan_pages = len([p for p in pages if p.get('incoming_links', 0) == 0])
    results['Health'] = {
        11: {'score': (total_pages - len(errors)) / max(total_pages, 1) * 100, 'name': 'Site Health Score'},
        12: {'score': len(errors), 'name': 'Total Errors'},
        13: {'score': warnings, 'name': 'Total Warnings'},
        14: {'score': notices, 'name': 'Total Notices'},
        15: {'score': total_pages, 'name': 'Total Crawled Pages'},
        16: {'score': indexed_pages, 'name': 'Total Indexed Pages'},
        19: {'score': (orphan_pages / max(total_pages, 1)) * 100, 'name': 'Orphan Pages %'}
    }

    # C. Crawlability & Indexation (21–40)
    statuses = [p.status for p in pages]
    http_2xx = sum(1 for s in statuses if 200 <= s < 300)
    http_3xx = sum(1 for s in statuses if 300 <= s < 400)
    http_4xx = sum(1 for s in statuses if 400 <= s < 500)
    http_5xx = sum(1 for s in statuses if 500 <= s < 600)
    broken_internal = len([p for p in pages if p.status >= 400 and urlparse(p.url).netloc == base_domain])
    broken_external = len([p for p in pages if p.status >= 400 and urlparse(p.url).netloc != base_domain])
    results['Crawlability'] = {
        21: {'score': http_2xx, 'name': 'HTTP 2xx Pages'},
        22: {'score': http_3xx, 'name': 'HTTP 3xx Pages'},
        23: {'score': http_4xx, 'name': 'HTTP 4xx Pages'},
        24: {'score': http_5xx, 'name': 'HTTP 5xx Pages'},
        27: {'score': broken_internal, 'name': 'Broken Internal Links'},
        28: {'score': broken_external, 'name': 'Broken External Links'},
        # Expand 25–26, 29–40 similarly with more crawler logic
    }

    # D. On-Page SEO (41–75) – sample pages
    missing_titles = 0
    duplicate_titles = set()
    missing_metas = 0
    missing_h1 = 0
    thin_content = 0
    for p in pages[:50]:
        soup = BeautifulSoup(p.html, 'lxml')
        title = soup.title.string if soup.title else ''
        if not title:
            missing_titles += 1
        else:
            duplicate_titles.add(title)
        meta = soup.find('meta', {'name': 'description'})
        if not meta or not meta.get('content'):
            missing_metas += 1
        h1 = soup.find('h1')
        if not h1 or not h1.text.strip():
            missing_h1 += 1
        text = soup.get_text(strip=True)
        if len(text) < 300:
            thin_content += 1
        # Expand for images, links, structured data (use json-ld parsing)
    results['OnPage'] = {
        41: {'score': missing_titles, 'name': 'Missing Title Tags'},
        42: {'score': len(duplicate_titles) - len(pages), 'name': 'Duplicate Title Tags'},
        45: {'score': missing_metas, 'name': 'Missing Meta Descriptions'},
        49: {'score': missing_h1, 'name': 'Missing H1'},
        52: {'score': thin_content, 'name': 'Thin Content Pages'}
        # Add 43–44, 46–48, 50–51, 53–75 similarly
    }

    # E. Performance & Technical (76–96)
    desktop_vitals = _pagespeed_insights(url, 'desktop')
    results['Performance'] = {
        76: {'score': desktop_vitals.get('LCP', 70), 'name': 'LCP'},
        77: {'score': desktop_vitals.get('FCP', 70), 'name': 'FCP'},
        78: {'score': desktop_vitals.get('CLS', 70), 'name': 'CLS'},
        79: {'score': desktop_vitals.get('TBT', 70), 'name': 'Total Blocking Time'},
        81: {'score': desktop_vitals.get('SpeedIndex', 70), 'name': 'Speed Index'},
        82: {'score': desktop_vitals.get('TTI', 70), 'name': 'Time to Interactive'},
        84: {'score': desktop_vitals.get('total_page_size', 0), 'name': 'Total Page Size (MB)'},
        85: {'score': desktop_vitals.get('requests_per_page', 0), 'name': 'Requests Per Page'},
        86: {'score': desktop_vitals.get('unminified_css', 100), 'name': 'Unminified CSS'},
        87: {'score': desktop_vitals.get('unminified_js', 100), 'name': 'Unminified JS'},
        88: {'score': desktop_vitals.get('render_blocking', 100), 'name': 'Render Blocking Resources'},
        89: {'score': desktop_vitals.get('dom_size', 0), 'name': 'Excessive DOM Size'},
        90: {'score': desktop_vitals.get('third_party_load', 100), 'name': 'Third-Party Script Load'},
        91: {'score': desktop_vitals.get('server_response_time', 200), 'name': 'Server Response Time'},
        92: {'score': desktop_vitals.get('image_optimization', 100), 'name': 'Image Optimization'},
        93: {'score': desktop_vitals.get('lazy_loading', 100), 'name': 'Lazy Loading Issues'},
        94: {'score': desktop_vitals.get('caching', 100), 'name': 'Browser Caching Issues'},
        95: {'score': desktop_vitals.get('compression', 100), 'name': 'Missing GZIP/Brotli'},
        # 96: Resource Load Errors – add from crawler
    }

    # F. Mobile, Security & International (97–150)
    mobile_vitals = _pagespeed_insights(url, 'mobile')
    mobile_friendly = _mobile_friendly_test(url)
    backlinks = _get_backlinks_info(url)
    results['MobileSecurityIntl'] = {
        97: {'score': mobile_friendly.get('mobile_friendly', 50), 'name': 'Mobile Friendly Test'},
        98: {'score': mobile_friendly.get('viewport', 100), 'name': 'Viewport Meta Tag'},
        101: {'score': mobile_vitals.get('overall_performance', 60), 'name': 'Mobile Core Web Vitals'},
        105: {'score': 100 if urlparse(url).scheme == 'https' else 20, 'name': 'HTTPS Implementation'},
        118: {'score': backlinks.get('domain_authority', 45), 'name': 'Domain Authority'},
        120: {'score': backlinks.get('total_backlinks', 1200), 'name': 'Total Backlinks'},
        121: {'score': backlinks.get('toxic_backlinks', 50), 'name': 'Toxic Backlinks'},
        # Expand 99–100, 102–104, 106–117, 119, 122–150 with more logic/APIs
    }

    # G. Competitor Analysis (151–167) – placeholder, add input param for competitors
    competitor_scores = {}
    if competitors:
        with ThreadPoolExecutor(max_workers=3) as executor:
            competitor_results = executor.map(analyze, competitors)
        for comp, comp_result in zip(competitors, competitor_results):
            comp_overall = comp_result['Health'][11]['score']  # example
            competitor_scores[comp] = {'health': comp_overall, 'da': 40}  # expand

    results['Competitor'] = {
        151: {'score': 75, 'name': 'Competitor Health Score'},
        # Expand with comparisons
    }

    # H. Broken Links Intelligence (168–180)
    broken_links = http_4xx + http_5xx
    results['BrokenLinks'] = {
        168: {'score': broken_links, 'name': 'Total Broken Links'},
        169: {'score': broken_internal, 'name': 'Internal Broken Links'},
        170: {'score': broken_external, 'name': 'External Broken Links'},
        # Expand 171–180 with trends/impact
    }

    # I. Opportunities, Growth & ROI (181–200) – placeholder AI-based
    results['OpportunitiesROI'] = {
        181: {'score': 80, 'name': 'High Impact Opportunities'},
        184: {'score': 65, 'name': 'Traffic Growth Forecast'},
        199: {'score': 70, 'name': 'ROI Forecast'},
        # Use LLM for text summaries
    }

    # A. Executive Summary – calculated at end
    overall_health = results['Health'][11]['score']
    grade = to_grade(overall_health)  # assume you have to_grade function
    results['Executive'] = {
        1: {'score': overall_health, 'name': 'Overall Site Health Score (%)'},
        2: {'score': grade, 'name': 'Website Grade (A+ to D)'},
        3: {'score': "AI-generated 200 word summary here (use Gemini)", 'name': 'Executive Summary'},
        # Expand 4–10 with lists/panels
    }

    return results
