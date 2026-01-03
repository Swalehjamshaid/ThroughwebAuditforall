
from .common import fetch, parse_html

def run(url: str) -> dict:
    metrics = {}
    resp = fetch(url)
    html = parse_html(resp.text)

    metrics['content_length_bytes'] = int(resp.headers.get('Content-Length', '0') or 0)
    scripts = len(html.find_all('script'))
    styles = len(html.find_all('link', rel=lambda x: x and 'stylesheet' in x))
    images = len(html.find_all('img'))
    metrics['scripts_count'] = scripts
    metrics['stylesheets_count'] = styles
    metrics['images_count'] = images

    return metrics
