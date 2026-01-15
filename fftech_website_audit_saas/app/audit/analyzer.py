from typing import Dict, List, Any
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup
from .crawler import simple_crawl  # Keep your existing crawler
from ..config import settings
import time
import re

def _pagespeed_core_web_vitals(url: str) -> Dict[str, float]:
    """
    Fetch real Core Web Vitals from Google PageSpeed Insights
    Returns scores 0–100 (higher = better)
    """
    if not settings.GOOGLE_PSI_API_KEY:
        return {'LCP': 70, 'FCP': 70, 'CLS': 70}  # fallback

    try:
        api = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
        params = {
            'url': url,
            'key': settings.GOOGLE_PSI_API_KEY,
            'category': ['performance'],
            'strategy': 'desktop'  # can add 'mobile' later
        }
        r = requests.get(api, params=params, timeout=30)
        if r.status_code != 200:
            return {'LCP': 50, 'FCP': 50, 'CLS': 50}

        data = r.json()
        lighthouse = data.get('lighthouseResult', {}).get('audits', {})

        def normalize(val, good, poor):
            if val is None:
                return 50
            if val <= good:
                return 100
            if val >= poor:
                return 0
            return round(100 * (poor - val) / (poor - good), 2)

        return {
            'LCP': normalize(lighthouse.get('largest-contentful-paint', {}).get('numericValue'), 2500, 4000),
            'FCP': normalize(lighthouse.get('first-contentful-paint', {}).get('numericValue'), 1800, 3000),
            'CLS': normalize(lighthouse.get('cumulative-layout-shift', {}).get('numericValue'), 0.1, 0.25),
            'TBT': normalize(lighthouse.get('total-blocking-time', {}).get('numericValue'), 200, 600),
            'SpeedIndex': normalize(lighthouse.get('speed-index', {}).get('numericValue'), 3400, 5800)
        }
    except Exception:
        return {'LCP': 60, 'FCP': 60, 'CLS': 60, 'TBT': 60, 'SpeedIndex': 60}


def analyze(url: str) -> Dict[str, Any]:
    """
    Comprehensive website audit analyzer – aims for 200+ metrics
    Returns structured results ready for grading & PDF
    """
    start_time = time.time()

    # 1. Crawl the site (use your simple_crawl or upgrade to Scrapy later)
    crawl_result = simple_crawl(url)
    pages = crawl_result.get('pages', [])
    errors = crawl_result.get('errors', [])
    total_pages = len(pages)

    # Parse URLs for better analysis
    parsed_url = urlparse(url)
    base_domain = parsed_url.netloc

    # 2. Collect raw metrics
    status_codes = [p.get('status', 0) for p in pages]
    http_2xx = sum(1 for s in status_codes if 200 <= s < 300)
    http_3xx = sum(1 for s in status_codes if 300 <= s < 400)
    http_4xx = sum(1 for s in status_codes if 400 <= s < 500)
    http_5xx = sum(1 for s in status_codes if 500 <= s < 600)

    # On-page & SEO metrics (sample first 50 pages to avoid timeout)
    missing_title = 0
    missing_meta_desc = 0
    missing_h1 = 0
    thin_content = 0
    large_images = 0
    broken_internal = 0
    broken_external = 0
    https_score = 100 if parsed_url.scheme == 'https' else 20

    for page in pages[:50]:
        html = page.get('html', '')
        if not html:
            continue
        soup = BeautifulSoup(html, 'lxml')

        # Title & Meta
        if not soup.title or not soup.title.string:
            missing_title += 1
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if not meta_desc or not meta_desc.get('content'):
            missing_meta_desc += 1

        # H1
        h1s = soup.find_all('h1')
        if not h1s or not any(h.get_text(strip=True) for h in h1s):
            missing_h1 += 1

        # Thin content (heuristic: < 300 chars text)
        text = soup.get_text(separator=' ', strip=True)
        if len(text) < 300:
            thin_content += 1

        # Images (heuristic)
        for img in soup.find_all('img'):
            if img.get('src') and not img.get('alt'):
                large_images += 1  # placeholder

        # Broken links (check status from crawler)
        # This needs better logic – for now count 4xx in internal links

    # Performance & Core Web Vitals
    vitals = _pagespeed_core_web_vitals(url)

    # Mobile & Security basics
    is_https = parsed_url.scheme == 'https'
    mobile_friendly = 85  # placeholder – use Google Mobile-Friendly Test API later

    # Structure results as per your categories (expandable)
    results = {
        'Executive': {
            'overall_score': 0,  # calculated later
            'grade': 'Pending',
            'executive_summary': f"Analyzed {total_pages} pages. {http_5xx} server errors found.",
            'strengths': ["Good HTTPS" if is_https else "Missing HTTPS"],
            'weaknesses': ["Multiple 4xx errors" if http_4xx > 5 else "Minor issues"],
            'priorities': ["Fix server errors", "Improve meta tags"]
        },
        'Health': {
            11: {'score': 100 - min(100, http_4xx*5 + http_5xx*10), 'name': 'Site Health Score'},
            12: {'score': http_4xx, 'name': 'Total Errors'},
            15: {'score': total_pages, 'name': 'Total Crawled Pages'}
        },
        'Crawlability': {
            21: {'score': http_2xx, 'name': 'HTTP 2xx Pages'},
            23: {'score': http_4xx, 'name': 'HTTP 4xx Pages'},
            24: {'score': http_5xx, 'name': 'HTTP 5xx Pages'},
        },
        'OnPage': {
            41: {'score': max(0, 100 - missing_title*10), 'name': 'Missing Title Tags'},
            45: {'score': max(0, 100 - missing_meta_desc*10), 'name': 'Missing Meta Descriptions'},
            49: {'score': max(0, 100 - missing_h1*10), 'name': 'Missing H1'}
        },
        'Performance': vitals,
        'MobileSecurityIntl': {
            97: {'score': mobile_friendly, 'name': 'Mobile Friendly'},
            105: {'score': https_score, 'name': 'HTTPS Implementation'}
        },
        'BrokenLinks': {
            168: {'score': http_4xx + http_5xx, 'name': 'Total Broken Links'}
        },
        'OpportunitiesROI': {
            181: {'score': 75, 'name': 'High Impact Opportunities'}  # placeholder
        }
    }

    # Final summary
    return {
        'url': url,
        'audit_time': round(time.time() - start_time, 2),
        'pages_crawled': total_pages,
        'errors': len(errors),
        'results': results,
        'raw': {
            'crawl_errors': errors[:10],
            'sample_pages': [p['url'] for p in pages[:5]]
        }
    }
