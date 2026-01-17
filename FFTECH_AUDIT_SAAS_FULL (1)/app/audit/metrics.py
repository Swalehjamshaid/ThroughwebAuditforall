from typing import Dict, Any
from .crawler import crawl_site
from ..integrations.psi import fetch_psi

def compute_metrics(url: str, max_pages: int = 150) -> Dict[str, Any]:
    crawl = crawl_site(url, max_pages=max_pages)

    http_2xx = sum(c for s,c in crawl.status_counts.items() if 200 <= s < 300)
    http_3xx = sum(c for s,c in crawl.status_counts.items() if 300 <= s < 400)
    http_4xx = sum(c for s,c in crawl.status_counts.items() if 400 <= s < 500)
    http_5xx = sum(c for s,c in crawl.status_counts.items() if 500 <= s < 600)

    titles = [p.get('title') for p in crawl.pages.values()]
    title_set = set(t for t in titles if t)
    missing_title = sum(1 for t in titles if not t)
    duplicate_title = len(titles) - len(title_set) if titles else 0

    metas = [p.get('meta_description') for p in crawl.pages.values()]
    missing_meta = sum(1 for m in metas if not m)

    missing_h1 = sum(1 for p in crawl.pages.values() if len(p.get('h1_list', [])) == 0)
    multiple_h1 = sum(1 for p in crawl.pages.values() if len(p.get('h1_list', [])) > 1)

    large_images = 0; missing_alt = 0
    for p in crawl.pages.values():
        for (src, alt) in p.get('images', []) or []:
            if src and any(src.lower().endswith(ext) for ext in ['.jpg','.jpeg','.png']) and 'compressed' not in (src or '').lower():
                large_images += 1
            if not (alt and alt.strip()): missing_alt += 1

    low_text_ratio = 0
    for p in crawl.pages.values():
        hlen = max(1, p.get('html_length', 1)); tlen = p.get('text_length', 0)
        ratio = (tlen / hlen) if hlen else 0
        if ratio < 0.1: low_text_ratio += 1

    og_missing = sum(1 for p in crawl.pages.values() if not (p.get('og',{}).get('title') and p.get('og',{}).get('description')))

    total_errors = http_4xx + http_5xx + len(crawl.broken_internal) + len(crawl.broken_external)
    total_warnings = len(crawl.redirect_chains)

    https_impl = url.lower().startswith('https://')

    metrics: Dict[str, Any] = {
        'total_crawled_pages': len(crawl.pages),
        'http_2xx_pages': http_2xx,
        'http_3xx_pages': http_3xx,
        'http_4xx_pages': http_4xx,
        'http_5xx_pages': http_5xx,
        'redirect_chains': len(crawl.redirect_chains),
        'broken_internal_links': len(crawl.broken_internal),
        'broken_external_links': len(crawl.broken_external),
        'missing_title_tags': missing_title,
        'duplicate_title_tags': duplicate_title,
        'missing_meta_descriptions': missing_meta,
        'missing_h1': missing_h1,
        'multiple_h1': multiple_h1,
        'missing_image_alt_tags': missing_alt,
        'large_uncompressed_images': large_images,
        'low_text_to_html_ratio_pages': low_text_ratio,
        'missing_open_graph_tags': og_missing,
        'https_implementation': https_impl,
        'lcp': 'unavailable','fcp':'unavailable','cls':'unavailable','total_blocking_time':'unavailable','speed_index':'unavailable','time_to_interactive':'unavailable',
    }

    psi = fetch_psi(url)
    if psi:
        metrics.update({k: psi.get(k, 'unavailable') for k in ['lcp','fcp','cls','total_blocking_time','speed_index','time_to_interactive']})

    quick_wins = 10
    if missing_title>0: quick_wins += 20
    if missing_meta>0: quick_wins += 20
    if metrics['missing_image_alt_tags']>0: quick_wins += 15
    if large_images>0: quick_wins += 15
    if http_4xx+http_5xx>0: quick_wins += 20
    metrics['quick_wins_score'] = min(100, quick_wins)

    metrics['total_errors'] = total_errors
    metrics['total_warnings'] = total_warnings
    metrics['total_notices'] = 0

    opps = []
    if large_images>0: opps.append('Compress & convert images to WebP/AVIF.')
    if missing_title>0: opps.append('Add unique, descriptive <title> tags to all pages.')
    if missing_meta>0: opps.append('Write compelling meta descriptions for key pages.')
    if http_4xx+http_5xx>0: opps.append('Resolve all 4xx/5xx errors; update/bypass broken links.')
    if og_missing>0: opps.append('Add Open Graph title/description for richer sharing.')
    metrics['high_impact_opportunities'] = opps

    return metrics
