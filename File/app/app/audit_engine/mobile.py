
from .common import fetch, parse_html

def run(url: str) -> dict:
    resp = fetch(url)
    html = parse_html(resp.text)
    metrics = {}
    viewport = html.find('meta', attrs={'name': 'viewport'})
    metrics['viewport_present'] = bool(viewport)
    return metrics
