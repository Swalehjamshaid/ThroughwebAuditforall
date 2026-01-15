
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Dict, Any, List, Set

DEFAULT_HEADERS = {'User-Agent': 'FFTechAuditBot/1.0 (+https://fftech.ai)'}

async def fetch(client: httpx.AsyncClient, url: str) -> Dict[str, Any]:
    try:
        r = await client.get(url, headers=DEFAULT_HEADERS, timeout=20)
        content_type = r.headers.get('content-type','')
        return {'url': url, 'status': r.status_code, 'headers': dict(r.headers), 'html': r.text if 'text/html' in content_type else ''}
    except Exception as e:
        return {'url': url, 'status': 0, 'headers': {}, 'html': '', 'error': str(e)}

async def crawl_site(start_url: str, max_pages: int = 50) -> List[Dict[str, Any]]:
    visited: Set[str] = set()
    to_visit: List[str] = [start_url]
    pages: List[Dict[str, Any]] = []
    base = urlparse(start_url).netloc

    async with httpx.AsyncClient(follow_redirects=True) as client:
        while to_visit and len(pages) < max_pages:
            url = to_visit.pop(0)
            if url in visited: continue
            visited.add(url)
            page = await fetch(client, url)
            pages.append(page)
            html = page.get('html','')
            if not html: continue
            soup = BeautifulSoup(html, 'lxml')
            for a in soup.find_all('a', href=True):
                href = urljoin(url, a['href'])
                p = urlparse(href)
                if p.netloc == base and p.scheme in ('http','https'):
                    if href not in visited and href not in to_visit:
                        to_visit.append(href)
    return pages
