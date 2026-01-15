from typing import Dict, Any, List
from .crawler import crawl_site
from .utils import clamp, invert_scale

async def analyze(url: str, competitors: List[str] | None = None) -> Dict[str, Any]:
    pages = await crawl_site(url, max_pages=30)
    total = len(pages)
    status_counts = {}
    html_sizes = []
    for p in pages:
        s = p.get('status', 0)
        status_counts[s] = status_counts.get(s,0)+1
        if p.get('html'): html_sizes.append(len(p['html']))
    http_2xx = sum(status_counts.get(k,0) for k in [200,201,204])
    http_3xx = sum(status_counts.get(k,0) for k in [301,302,304])
    http_4xx = sum(status_counts.get(k,0) for k in [400,401,403,404,410])
    http_5xx = sum(status_counts.get(k,0) for k in [500,502,503,504])

    avg_page_size = sum(html_sizes)/len(html_sizes) if html_sizes else 0
    requests_per_page = 30

    missing_title = 0; missing_meta_desc = 0
    for p in pages:
        h = p.get('html','').lower()
        if not h: continue
        if '<title' not in h: missing_title += 1
        if 'meta name="description"' not in h and "meta name='description'" not in h:
            missing_meta_desc += 1

    crawlability_score = clamp(100 - (http_4xx + http_5xx) * 5 - http_3xx * 1)
    onpage_score = clamp(100 - (missing_title + missing_meta_desc) * 2)
    performance_score = clamp(invert_scale(avg_page_size, max_value=500000))
    mobile_sec_intl_score = 80.0

    category_scores = {
        'executive': (crawlability_score*0.25 + onpage_score*0.35 + performance_score*0.3 + mobile_sec_intl_score*0.1),
        'overall': crawlability_score*0.4 + onpage_score*0.4 + performance_score*0.2,
        'crawlability': crawlability_score,
        'onpage': onpage_score,
        'performance': performance_score,
        'mobile_security_intl': mobile_sec_intl_score,
        'opportunities': 70.0,
    }

    metrics = {
        'http_2xx': http_2xx,
        'http_3xx': http_3xx,
        'http_4xx': http_4xx,
        'http_5xx': http_5xx,
        'total_crawled_pages': total,
        'missing_title': missing_title,
        'missing_meta_desc': missing_meta_desc,
        'total_page_size': int(avg_page_size),
        'requests_per_page': requests_per_page,
    }

    return {
        'pages': pages,
        'metrics': metrics,
        'category_scores': {k: round(v,2) for k,v in category_scores.items()}
    }