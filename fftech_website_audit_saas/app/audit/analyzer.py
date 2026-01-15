
from .crawler import simple_crawl
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import requests

from ..config import settings


def _pagespeed_core_web_vitals(url: str):
    if not settings.GOOGLE_PSI_API_KEY:
        return {}
    try:
        api = 'https://www.googleapis.com/pagespeedonline/v5/runPagespeed'
        params = {'url': url, 'key': settings.GOOGLE_PSI_API_KEY, 'category': 'performance', 'strategy': 'desktop'}
        r = requests.get(api, params=params, timeout=20)
        if r.status_code != 200:
            return {}
        data = r.json()
        lighthouse = data.get('lighthouseResult', {}).get('audits', {})
        lcp = lighthouse.get('largest-contentful-paint', {}).get('numericValue')
        fcp = lighthouse.get('first-contentful-paint', {}).get('numericValue')
        cls = lighthouse.get('cumulative-layout-shift', {}).get('numericValue')
        # Simple mapping to 0-100 (lower is better for lcp/fcp/cls)
        def score_from(val, good, poor):
            if val is None:
                return 50
            if val <= good:
                return 100
            if val >= poor:
                return 0
            # Linear
            return round(100 * (poor - val) / (poor - good), 2)
        return {
            'LCP': score_from(lcp, 2500, 4000),
            'FCP': score_from(fcp, 1800, 3000),
            'CLS': score_from(cls, 0.1, 0.25)
        }
    except Exception:
        return {}


def analyze(url: str):
    crawl = simple_crawl(url)
    pages = crawl.pages
    total_pages = len(pages)
    statuses = [p['status'] for p in pages]
    status_4xx = sum(1 for s in statuses if 400 <= s < 500)
    status_5xx = sum(1 for s in statuses if 500 <= s < 600)

    missing_titles = sum(1 for p in pages if not p['title'])
    missing_meta = 0
    missing_h1 = 0
    large_images = 0
    for p in pages[:20]:
        soup = BeautifulSoup(p['html'], 'lxml')
        md = soup.select_one('meta[name="description"]')
        if not md or not md.get('content'):
            missing_meta += 1
        h1 = soup.select_one('h1')
        if not h1 or not h1.get_text(strip=True):
            missing_h1 += 1
        for img in soup.select('img[src]'):
            src = (img.get('src') or '')
            if any(src.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png']):
                # heuristic only
                large_images += 0

    vitals = _pagespeed_core_web_vitals(url)

    results = {
        'Executive': {
            1: {'score': 100 if status_5xx == 0 else max(0, 100 - status_5xx*10), 'weight': 3},
            2: {'score': None, 'weight': 0},
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
            'crawl_errors': crawl.errors[:10],
            'sample_pages': [p['url'] for p in pages[:10]]
        }
    }
