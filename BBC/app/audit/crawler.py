import urllib.parse as urlparse
from collections import defaultdict, deque
from typing import Dict, List, Set, Tuple
import requests
from bs4 import BeautifulSoup

USER_AGENT = 'FFTechAuditBot/1.0 (+https://fftech.example)'

class CrawlResult:
    def __init__(self):
        self.pages: Dict[str, Dict] = {}
        self.broken_internal: List[Tuple[str, str, int]] = []
        self.broken_external: List[Tuple[str, str, int]] = []
        self.status_counts: Dict[int, int] = defaultdict(int)
        self.redirect_chains: List[List[str]] = []
        self.start_url: str | None = None

def normalize_url(base: str, href: str) -> str | None:
    if not href: return None
    href = href.strip()
    if href.startswith('#'): return None
    url = urlparse.urljoin(base, href)
    parsed = urlparse.urlparse(url)
    if parsed.scheme not in ('http','https'): return None
    return urlparse.urlunparse(parsed._replace(fragment=''))

def crawl_site(start_url: str, max_pages: int = 200, timeout: int = 10) -> CrawlResult:
    res = CrawlResult(); res.start_url = start_url
    seen: Set[str] = set(); domain = urlparse.urlparse(start_url).netloc
    q = deque([start_url])
    while q and len(seen) < max_pages:
        url = q.popleft()
        if url in seen: continue
        seen.add(url)
        try:
            r = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=timeout, allow_redirects=True)
            status = r.status_code; res.status_counts[status]+=1
            if 300 <= status < 400:
                chain = [h.headers.get('Location','') for h in r.history] + [url]
                if len(chain)>2: res.redirect_chains.append(chain)
            if status >= 400:
                res.pages[url] = {"status": status, "links": []}
                continue
            soup = BeautifulSoup(r.text, 'lxml')
            title = (soup.title.string.strip() if soup.title and soup.title.string else None)
            meta_desc_tag = soup.find('meta', attrs={'name':'description'})
            meta_desc = meta_desc_tag.get('content') if meta_desc_tag else None
            h1s = [h.get_text(strip=True) for h in soup.find_all('h1')]
            imgs = [(img.get('src'), img.get('alt')) for img in soup.find_all('img')]
            links=[]
            for a in soup.select('a[href]'):
                nu = normalize_url(url, a.get('href'))
                if not nu: continue
                links.append(nu)
                if urlparse.urlparse(nu).netloc == domain and nu not in seen:
                    q.append(nu)
            og_title = soup.find('meta', property='og:title')
            og_desc = soup.find('meta', property='og:description')
            viewport = soup.find('meta', attrs={'name':'viewport'})
            res.pages[url] = {
                'status': status,
                'title': title,
                'meta_description': meta_desc,
                'h1_list': h1s,
                'images': imgs,
                'links': links,
                'og': {'title': bool(og_title and og_title.get('content')), 'description': bool(og_desc and og_desc.get('content'))},
                'viewport': bool(viewport),
                'html_length': len(r.text),
                'text_length': len(soup.get_text(' ', strip=True))
            }
        except requests.RequestException:
            res.status_counts[0]+=1
            res.pages[url] = {"status": 0, "links": []}
    for page, pdata in res.pages.items():
        for link in pdata.get('links', []):
            try:
                hr = requests.head(link, headers={'User-Agent': USER_AGENT}, timeout=5, allow_redirects=True)
                code = hr.status_code
            except requests.RequestException:
                code = 0
            if urlparse.urlparse(link).netloc == domain:
                if code>=400 or code==0: res.broken_internal.append((page, link, code))
            else:
                if code>=400 or code==0: res.broken_external.append((page, link, code))
    return res
