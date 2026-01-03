
from .common import fetch, parse_html

def run(url: str) -> dict:
    resp = fetch(url)
    html = parse_html(resp.text)
    metrics = {}
    hreflangs = html.find_all('link', attrs={'rel': 'alternate', 'hreflang': True})
    metrics['hreflang_count'] = len(hreflangs)
    return metrics
