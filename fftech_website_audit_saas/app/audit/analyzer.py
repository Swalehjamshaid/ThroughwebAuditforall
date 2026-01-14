import asyncio
import httpx
from bs4 import BeautifulSoup
from .crawler import simple_crawl
from ..config import settings

async def _fetch_vitals(client, url):
    if not settings.GOOGLE_PSI_API_KEY: return {}
    try:
        api = 'https://www.googleapis.com/pagespeedonline/v5/runPagespeed'
        r = await client.get(api, params={'url': url, 'key': settings.GOOGLE_PSI_API_KEY}, timeout=30)
        data = r.json()
        audits = data.get('lighthouseResult', {}).get('audits', {})
        return {
            'LCP': audits.get('largest-contentful-paint', {}).get('numericValue'),
            'CLS': audits.get('cumulative-layout-shift', {}).get('numericValue')
        }
    except: return {}

async def analyze(url: str):
    crawl = simple_crawl(url) # Your existing crawler
    pages = crawl.pages
    
    async with httpx.AsyncClient() as client:
        vitals = await _fetch_vitals(client, url)

    # Simplified Metric Scoring
    results = {
        'Health': {
            11: {'score': 90 if len(pages) > 1 else 50, 'weight': 3},
        },
        'OnPage': {
            41: {'score': 100 if pages[0].get('title') else 0, 'weight': 2},
        },
        'Performance': {
            76: {'score': 100 if not vitals.get('LCP') or vitals['LCP'] < 2500 else 50, 'weight': 2},
        }
    }
    return {'results': results, 'pages': len(pages)}
