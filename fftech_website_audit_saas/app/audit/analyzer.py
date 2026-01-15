from typing import Dict, Any, List
from .crawler import crawl_site
from .utils import clamp, invert_scale

async def analyze(url: str, competitors: List[str] | None = None) -> Dict[str, Any]:
    pages = await crawl_site(url, max_pages=30)
    total = len(pages)

    # Status distribution
    status_counts = {}
    html_sizes = []
    for p in pages:
        s = p.get('status',0)
        status_counts[s] = status_counts.get(s,0) + 1
        if p.get('html'): html_sizes.append(len(p['html']))

    http_2xx = sum(status_counts.get(k,0) for k in [200,201,204])
    http_3xx = sum(status_counts.get(k,0) for k in [301,302,304])
    http_4xx = sum(status_counts.get(k,0) for k in [400,401,403,404,410])
    http_5xx = sum(status_counts.get(k,0) for k in [500,502,503,504])

    # On-page quick checks
    missing_title = 0
    missing_meta_desc = 0
    broken_anchor_links = 0
    for p in pages:
        html = p.get('html','').lower()
        if not html: continue
        if '<title' not in html: missing_title += 1
        if 'meta name="description"' not in html and "meta name='description'" not in html: missing_meta_desc += 1
        # Very rough anchor check (#id doesn’t exist)
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')
            ids = {tag.get('id') for tag in soup.find_all(attrs={'id': True})}
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('#') and href[1:] and href[1:] not in ids:
                    broken_anchor_links += 1
        except Exception:
            pass

    avg_html_size = int(sum(html_sizes)/len(html_sizes)) if html_sizes else 0

    # Derived scores (proxy-based; integrate PSI/Lighthouse later)
    crawlability_score = clamp(100 - (http_4xx + http_5xx) * 4 - http_3xx * 1)
    onpage_score = clamp(100 - (missing_title + missing_meta_desc + broken_anchor_links*0.2) * 2)
    performance_score = clamp(invert_scale(avg_html_size, 500_000))
    mobile_sec_intl_score = 78.0  # placeholder baseline

    category_scores = {
        'executive': round(crawlability_score*0.25 + onpage_score*0.35 + performance_score*0.3 + mobile_sec_intl_score*0.1, 2),
        'overall': round(crawlability_score*0.4 + onpage_score*0.4 + performance_score*0.2, 2),
        'crawlability': round(crawlability_score,2),
        'onpage': round(onpage_score,2),
        'performance': round(performance_score,2),
        'mobile_security_intl': round(mobile_sec_intl_score,2),
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
        'broken_anchor_links': broken_anchor_links,
        'total_page_size': avg_html_size,
        'requests_per_page': 30,
    }

    # Severity indicator (simple):
    severity = min(100, http_4xx*5 + http_5xx*10 + missing_title*2 + missing_meta_desc*2)
    metrics['risk_severity_index'] = severity

    # Competitors (shallow comparison):
    comp = []
    if competitors:
        for c in competitors[:3]:
            try:
                r = await analyze(c, competitors=None)  # shallow recursion
                comp.append({'url': c, 'overall': r['category_scores']['overall']})
            except Exception:
                comp.append({'url': c, 'overall': 0})
    metrics['competitors'] = comp

    return {'pages': pages, 'metrics': metrics, 'category_scores': category_scores}