import asyncio
import httpx
import logging
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from .crawler import simple_crawl
from ..config import settings

logger = logging.getLogger(__name__)

async def _fetch_pagespeed_vitals(client: httpx.AsyncClient, url: str):
    """Asynchronously fetches Google PageSpeed Insights (Metric Category E)"""
    if not settings.GOOGLE_PSI_API_KEY:
        return {}
    
    try:
        api_url = 'https://www.googleapis.com/pagespeedonline/v5/runPagespeed'
        params = {
            'url': url, 
            'key': settings.GOOGLE_PSI_API_KEY, 
            'category': 'performance', 
            'strategy': 'desktop'
        }
        # Using 30s timeout for PSI as it performs heavy rendering
        response = await client.get(api_url, params=params, timeout=30.0)
        
        if response.status_code != 200:
            return {}
        
        data = response.json()
        audits = data.get('lighthouseResult', {}).get('audits', {})
        
        # Extract Core Web Vitals
        lcp = audits.get('largest-contentful-paint', {}).get('numericValue')
        fcp = audits.get('first-contentful-paint', {}).get('numericValue')
        cls = audits.get('cumulative-layout-shift', {}).get('numericValue')

        def score_metric(val, good, poor):
            if val is None: return 50
            if val <= good: return 100
            if val >= poor: return 0
            return round(100 * (poor - val) / (poor - good), 2)

        return {
            'LCP': score_metric(lcp, 2500, 4000),
            'FCP': score_metric(fcp, 1800, 3000),
            'CLS': score_metric(cls, 0.1, 0.25)
        }
    except Exception as e:
        logger.error(f"PSI API Failure: {e}")
        return {}

async def analyze(url: str):
    """
    Main Powerful Analyzer: Orchestrates crawling and multi-category analysis
    """
    # 1. Start the Crawl (Synchronous part of your current logic)
    crawl = simple_crawl(url)
    pages = crawl.pages
    
    # 2. Parallel Processing for heavy tasks
    async with httpx.AsyncClient() as client:
        # Fetch PageSpeed data while we simultaneously process HTML
        vitals_task = asyncio.create_task(_fetch_pagespeed_vitals(client, url))
        
        # Internal Metrics Processing
        total_pages = len(pages)
        statuses = [p['status'] for p in pages]
        status_4xx = sum(1 for s in statuses if 400 <= s < 500)
        status_5xx = sum(1 for s in statuses if 500 <= s < 600)

        missing_titles = 0
        missing_meta = 0
        missing_h1 = 0
        total_images = 0
        missing_alt = 0

        # Analyze up to 30 pages for deep On-Page metrics (Category D)
        for p in pages[:30]:
            try:
                soup = BeautifulSoup(p['html'], 'lxml')
                
                # Title Check
                if not p.get('title') or len(p['title']) < 10:
                    missing_titles += 1
                
                # Meta Description Check
                meta_desc = soup.find('meta', attrs={'name': 'description'})
                if not meta_desc or not meta_desc.get('content'):
                    missing_meta += 1
                
                # H1 Check
                h1 = soup.find('h1')
                if not h1 or not h1.get_text(strip=True):
                    missing_h1 += 1

                # Image Alt Tags (Metric 55)
                imgs = soup.find_all('img')
                total_images += len(imgs)
                missing_alt += sum(1 for img in imgs if not img.get('alt'))
                
            except Exception:
                continue

        # Wait for the external API task to finish
        vitals = await vitals_task

    # 3. Enhanced Scoring Engine (Mapped to your Numbered Categories)
    results = {
        'Executive': { # Category A
            1: {'score': 100 if status_5xx == 0 else max(0, 100 - status_5xx * 15), 'weight': 3},
            3: {'score': 85 if total_pages > 5 else 60, 'weight': 1},
            8: {'score': 100 - (status_4xx * 2), 'weight': 2},
        },
        'Health': { # Category B
            11: {'score': 100 - min(100, (status_4xx * 5) + (status_5xx * 20)), 'weight': 3},
            12: {'score': max(0, 100 - status_4xx * 10), 'weight': 2},
        },
        'OnPage': { # Category D
            41: {'score': max(0, 100 - (missing_titles / min(30, total_pages)) * 100), 'weight': 2},
            45: {'score': max(0, 100 - (missing_meta / min(30, total_pages)) * 100), 'weight': 2},
            55: {'score': max(0, 100 - (missing_alt / (total_images or 1)) * 100), 'weight': 2},
        },
        'Performance': { # Category E
            76: {'score': vitals.get('LCP', 65), 'weight': 3},
            78: {'score': vitals.get('CLS', 65), 'weight': 2},
            85: {'score': 90 if total_images < 50 else 70, 'weight': 1},
        },
        'Security': { # Category F
            105: {'score': 100 if url.startswith('https') else 0, 'weight': 3},
            108: {'score': 100 if "strict-transport-security" in str(pages[0].get('html')).lower() else 50, 'weight': 1}
        }
    }

    return {
        'pages': total_pages,
        'status_4xx': status_4xx,
        'status_5xx': status_5xx,
        'vitals': vitals,
        'results': results,
        'timestamp': asyncio.get_event_loop().time()
    }
