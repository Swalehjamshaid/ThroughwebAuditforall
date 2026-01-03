
from .common import fetch, parse_html

def run(url: str) -> dict:
    resp = fetch(url)
    html = parse_html(resp.text)
    metrics = {}
    title_tag = html.find('title')
    metrics['title_exists'] = bool(title_tag)
    metrics['title_length'] = len(title_tag.text) if title_tag else 0
    meta_desc = html.find('meta', attrs={'name': 'description'})
    metrics['meta_description_exists'] = bool(meta_desc)
    metrics['meta_description_length'] = len(meta_desc['content']) if meta_desc and meta_desc.get('content') else 0
    h1 = html.find('h1')
    metrics['h1_exists'] = bool(h1)
    return metrics
