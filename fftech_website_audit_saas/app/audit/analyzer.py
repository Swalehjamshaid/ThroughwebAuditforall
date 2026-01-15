import asyncio
from typing import Dict, Any, List
from .crawler import crawl_site
from .utils import clamp, invert_scale

async def analyze_one(url: str, max_pages: int = 30) -> Dict[str, Any]:
    pages = await crawl_site(url, max_pages=max_pages)
    total = len(pages)
    status_counts = {}
    html_sizes = []
    missing_title = 0
    missing_meta = 0
    h1_missing = 0

    for p in pages:
        s = p.get('status',0)
        status_counts[s] = status_counts.get(s,0) + 1
        html = p.get('html','')
        if html:
            html_sizes.append(len(html))
            low = html.lower()
            if '<title' not in low: missing_title += 1
            if 'meta name="description"' not in low and "meta name='description'" not in low: missing_meta += 1
            if '<h1' not in low: h1_missing += 1

    http_2xx = sum(status_counts.get(k,0) for k in [200,201,204])
    http_3xx = sum(status_counts.get(k,0) for k in [301,302,304])
    http_4xx = sum(status_counts.get(k,0) for k in [400,401,403,404,410])
    http_5xx = sum(status_counts.get(k,0) for k in [500,502,503,504])

    avg_html_size = int(sum(html_sizes)/len(html_sizes)) if html_sizes else 0

    crawlability_score = clamp(100 - (http_4xx + http_5xx)*5 - http_3xx*1)
    onpage_score = clamp(100 - (missing_title + missing_meta + h1_missing)*1.5)
    performance_score = clamp(invert_scale(avg_html_size, 600000))
    mobile_sec_intl_score = 80.0

    metrics = {
        'http_2xx': http_2xx,
        'http_3xx': http_3xx,
        'http_4xx': http_4xx,
        'http_5xx': http_5xx,
        'total_crawled_pages': total,
        'missing_title': missing_title,
        'missing_meta_desc': missing_meta,
        'missing_h1': h1_missing,
        'total_page_size': avg_html_size,
        'requests_per_page': 30,
    }

    category_scores = {
        'executive': (crawlability_score*0.25 + onpage_score*0.35 + performance_score*0.3 + mobile_sec_intl_score*0.1),
        'overall': crawlability_score*0.4 + onpage_score*0.4 + performance_score*0.2,
        'crawlability': crawlability_score,
        'onpage': onpage_score,
        'performance': performance_score,
        'mobile_security_intl': mobile_sec_intl_score,
        'opportunities': 70.0
    }

    return { 'pages': pages, 'metrics': metrics, 'category_scores': {k: round(v,2) for k,v in category_scores.items()} }

async def analyze(url: str, competitors: List[str] | None = None) -> Dict[str, Any]:
    primary = await analyze_one(url)
    comp_results = {}
    if competitors:
        for c in competitors[:3]:
            try:
                comp_results[c] = await analyze_one(c, max_pages=15)
            except Exception:
                comp_results[c] = {'category_scores': {}, 'metrics': {}}
    return {'primary': primary, 'competitors': comp_results}