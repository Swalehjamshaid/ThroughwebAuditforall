from typing import Dict, Any
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from .crawler import simple_crawl
from ..config import settings


def _pagespeed_core_web_vitals(url: str) -> Dict[str, float]:
    """
    Fetch real Core Web Vitals from Google PageSpeed Insights.
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
            'strategy': 'desktop'
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
        }
    except Exception:
        return {'LCP': 60, 'FCP': 60, 'CLS': 60}


def analyze(url: str) -> Dict[str, Any]:
    """
    Main website audit analyzer function.
    Safely handles CrawlResult as object or dict.
    """
    # Run crawl
    crawl_result = simple_crawl(url)

    # Safely extract pages & errors (handles both object and dict)
    if isinstance(crawl_result, dict):
        pages = crawl_result.get('pages', [])
        errors = crawl_result.get('errors', [])
    else:
        # Assume it's a custom object (CrawlResult)
        pages = getattr(crawl_result, 'pages', []) or []
        errors = getattr(crawl_result, 'errors', []) or []

    total_pages = len(pages)

    # Extract status codes safely
    statuses = []
    for p in pages:
        if isinstance(p, dict) and 'status' in p:
            statuses.append(p['status'])
        elif hasattr(p, 'status'):
            statuses.append(p.status)

    status_4xx = sum(1 for s in statuses if 400 <= s < 500)
    status_5xx = sum(1 for s in statuses if 500 <= s < 600)

    # On-page metrics (sample first 20 pages)
    missing_titles = 0
    missing_meta = 0
    missing_h1 = 0
    large_images = 0

    for p in pages[:20]:
        html = getattr(p, 'html', '') if not isinstance(p, dict) else p.get('html', '')
        if not html:
            continue

        soup = BeautifulSoup(html, 'lxml')

        # Title
        if not soup.title or not soup.title.string:
            missing_titles += 1

        # Meta description
        md = soup.select_one('meta[name="description"]')
        if not md or not md.get('content'):
            missing_meta += 1

        # H1
        h1 = soup.select_one('h1')
        if not h1 or not h1.get_text(strip=True):
            missing_h1 += 1

        # Simple image check (heuristic)
        for img in soup.select('img[src]'):
            large_images += 0  # placeholder - can improve later

    # Get Core Web Vitals
    vitals = _pagespeed_core_web_vitals(url)

    # Build results structure
    results = {
        'Executive': {
            1: {'score': 100 if status_5xx == 0 else max(0, 100 - status_5xx*10), 'weight': 3},
            2: {'score': None, 'weight': 0},  # grade will be filled later
            8: {'score': 100, 'weight': 2},
        },
        'Health': {
            11: {'score': 100 - min(100, status_4xx*5 + status_5xx*10), 'weight': 3},
            12: {'score': max(0, 100 - status_4xx*10), 'weight': 2},
            15: {'score': 60 + min(40, total_pages), 'weight': 1},
        },
        'OnPage': {
            41: {'score': max(0, 100 - missing_titles*10), 'weight': 2},
            45: {'score': max(0, 100 - missing_meta*10), 'weight': 2},
            49: {'score': max(0, 100 - missing_h1*10), 'weight': 2},
        },
        'Performance': {
            76: {'score': vitals.get('LCP', 70), 'weight': 2},
            77: {'score': vitals.get('FCP', 70), 'weight': 1},
            78: {'score': vitals.get('CLS', 70), 'weight': 2},
            91: {'score': 70, 'weight': 1},
        },
        'MobileSecurityIntl': {
            105: {'score': 90 if urlparse(url).scheme == 'https' else 20, 'weight': 2},
            110: {'score': 60, 'weight': 1},
        },
        'BrokenLinks': {
            168: {'score': 95, 'weight': 1},
        },
        'OpportunitiesROI': {
            182: {'score': 70, 'weight': 1},
            189: {'score': 70, 'weight': 1},
            199: {'score': 70, 'weight': 1},
        }
    }

    return {
        'pages': total_pages,
        'status_4xx': status_4xx,
        'status_5xx': status_5xx,
        'results': results,
        'raw': {
            'crawl_errors': errors[:10],
            'sample_pages': [getattr(p, 'url', p.get('url', '')) for p in pages[:10]]
        }
    }
