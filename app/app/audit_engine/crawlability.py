
from .common import fetch, parse_html
from urllib.parse import urljoin

def run(url: str) -> dict:
    metrics = {}
    resp = fetch(url)
    metrics['http_status'] = resp.status_code
    metrics['final_url'] = str(resp.url)

    html = parse_html(resp.text)
    internal_broken = 0
    external_broken = 0
    total_links = 0
    for a in html.find_all('a'):
        href = a.get('href')
        if not href:
            continue
        total_links += 1
        link = urljoin(url, href)
        try:
            r = fetch(link)
            if r.status_code >= 400:
                if link.startswith(url):
                    internal_broken += 1
                else:
                    external_broken += 1
        except Exception:
            if link.startswith(url):
                internal_broken += 1
            else:
                external_broken += 1
    metrics['total_links'] = total_links
    metrics['broken_internal_links'] = internal_broken
    metrics['broken_external_links'] = external_broken

    try:
        rbt = fetch(url.rstrip('/') + '/robots.txt')
        metrics['robots_txt_status'] = rbt.status_code
    except Exception:
        metrics['robots_txt_status'] = 'error'
    try:
        sm = fetch(url.rstrip('/') + '/sitemap.xml')
        metrics['sitemap_xml_status'] = sm.status_code
    except Exception:
        metrics['sitemap_xml_status'] = 'error'

    return metrics
