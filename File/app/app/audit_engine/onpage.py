
from .common import fetch, parse_html

def run(url: str) -> dict:
    resp = fetch(url)
    html = parse_html(resp.text)
    metrics = {}

    title = html.find('title')
    metrics['title_exists'] = bool(title)
    metrics['title_length'] = len(title.text.strip()) if title else 0
    meta_desc = html.find('meta', attrs={'name': 'description'})
    metrics['meta_description_exists'] = bool(meta_desc)
    metrics['meta_description_length'] = len(meta_desc.get('content','')) if meta_desc else 0
    h1 = html.find('h1')
    metrics['h1_exists'] = bool(h1)

    imgs = html.find_all('img')
    missing_alt = 0
    large_images = 0
    for img in imgs:
        if not img.get('alt'):
            missing_alt += 1
        src = img.get('src')
        if src:
            try:
                r = fetch(src)
                size = int(r.headers.get('Content-Length','0') or 0)
                if size > 500_000:
                    large_images += 1
            except Exception:
                pass
    metrics['images_missing_alt'] = missing_alt
    metrics['large_images'] = large_images

    ldjson = html.find('script', attrs={'type':'application/ld+json'})
    metrics['structured_data_present'] = bool(ldjson)
    metrics['og_tags_present'] = bool(html.find('meta', property=lambda v: v and v.startswith('og:')))
    metrics['twitter_cards_present'] = bool(html.find('meta', attrs={'name':'twitter:card'}))

    return metrics
