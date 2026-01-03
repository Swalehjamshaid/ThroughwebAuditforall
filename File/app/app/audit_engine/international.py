
from .common import fetch, parse_html

def run(url: str) -> dict:
    resp = fetch(url)
    html = parse_html(resp.text)
    metrics = {}
    hreflangs = html.find_all('link', attrs={'rel': 'alternate', 'hreflang': True})
    metrics['hreflang_count'] = len(hreflangs)
    codes = {}
    conflicts = 0
    for h in hreflangs:
        code = h.get('hreflang')
        href = h.get('href')
        if code in codes and codes[code] != href:
            conflicts += 1
        codes[code] = href
    metrics['hreflang_conflicts'] = conflicts
    return metrics
