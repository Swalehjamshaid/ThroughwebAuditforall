
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from collections import deque

DEFAULT_MAX_PAGES = 30
DEFAULT_TIMEOUT = 10

class CrawlResult:
    def __init__(self):
        self.pages = []
        self.errors = []

def simple_crawl(start_url: str, max_pages: int = DEFAULT_MAX_PAGES) -> CrawlResult:
    seen = set()
    q = deque([start_url])
    base_netloc = urlparse(start_url).netloc
    result = CrawlResult()

    while q and len(result.pages) < max_pages:
        url = q.popleft()
        if url in seen:
            continue
        seen.add(url)
        try:
            resp = requests.get(url, timeout=DEFAULT_TIMEOUT, headers={'User-Agent': 'FFTechAuditBot/1.0'})
            status = resp.status_code
            soup = BeautifulSoup(resp.text, 'lxml')
            title = (soup.title.string or '').strip() if soup.title else ''
            links = []
            for a in soup.select('a[href]'):
                href = a.get('href')
                full = urljoin(url, href)
                links.append(full)
                if urlparse(full).netloc == base_netloc:
                    q.append(full)
            images = [img.get('src') for img in soup.select('img[src]')]
            result.pages.append({'url': url, 'status': status, 'title': title, 'links': links, 'images': images, 'html': resp.text})
        except Exception as e:
            result.errors.append({'url': url, 'error': str(e)})
    return result
