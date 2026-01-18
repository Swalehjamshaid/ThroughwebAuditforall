
import asyncio
import aiohttp
from urllib.parse import urlparse, urljoin
from typing import Dict, List, Set, Tuple
from .extractor import basic_onpage_checks

DEFAULT_MAX_PAGES = 50
TIMEOUT = aiohttp.ClientTimeout(total=20)
HEADERS = {"User-Agent": "FFTechAuditBot/1.0 (+https://fftech.ai)"}

async def fetch(session: aiohttp.ClientSession, url: str) -> Tuple[int, str, Dict[str, str]]:
    try:
        async with session.get(url, timeout=TIMEOUT, allow_redirects=True) as resp:
            status = resp.status
            text = await resp.text(errors='ignore')
            return status, text, dict(resp.headers)
    except Exception:
        return 0, '', {}

async def crawl(base_url: str, max_pages: int = DEFAULT_MAX_PAGES) -> Dict:
    parsed = urlparse(base_url)
    domain = f"{parsed.scheme}://{parsed.netloc}"

    visited: Set[str] = set()
    to_visit: List[str] = [domain]
    results = {}

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        while to_visit and len(visited) < max_pages:
            url = to_visit.pop(0)
            if url in visited: continue
            status, html, headers = await fetch(session, url)
            visited.add(url)
            page = {"status": status, "headers": headers}
            if status and html:
                page.update(basic_onpage_checks(url, html))
            results[url] = page
            # enqueue internal links (very basic)
            if html:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, 'lxml')
                for a in soup.find_all('a'):
                    href = a.get('href')
                    if not href: continue
                    if href.startswith('#'): continue
                    if href.startswith('http'):
                        if urlparse(href).netloc == parsed.netloc:
                            to_visit.append(href)
                    elif href.startswith('/'):
                        to_visit.append(urljoin(domain, href))
        
    return {
        'domain': domain,
        'pages': results,
        'total_pages': len(results)
    }
