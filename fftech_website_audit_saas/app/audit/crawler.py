import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Dict, Any, List, Set

DEFAULT_HEADERS = {'User-Agent': 'FFTechAuditBot/1.0 (+https://fftech.ai)'}

async def fetch(client: httpx.AsyncClient, url: str) -> Dict[str, Any]:
    try:
        r = await client.get(url, headers=DEFAULT_HEADERS, timeout=20)
        ctype = r.headers.get('content-type','')
        return {'url':url,'status':r.status_code,'headers':dict(r.headers),'html': r.text if 'text/html' in ctype else ''}
    except Exception as e:
        return {'url': url, 'status':0, 'headers':{}, 'html':'', 'error': str(e)}

async def crawl_site(start_url: str, max_pages: int = 50) -> List[Dict[str, Any]]:
    visited: Set[str] = set()
    queue: List[str] = [start_url]
    out: List[Dict[str, Any]] = []
    root = urlparse(start_url)
    host = root.netloc
    async with httpx.AsyncClient(follow_redirects=True) as client:
        while queue and len(out) < max_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            page = await fetch(client, url)
            out.append(page)
            html = page.get('html','')
            if not html:
                continue
            soup = BeautifulSoup(html, 'lxml')
            for a in soup.find_all('a', href=True):
                href = urljoin(url, a['href'])
                p = urlparse(href)
                if p.scheme in ('http','https') and p.netloc == host:
                    if href not in visited and href not in queue:
                        queue.append(href)
    return out