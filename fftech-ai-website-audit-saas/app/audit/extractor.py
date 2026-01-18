
from bs4 import BeautifulSoup
from typing import Dict
import re

def parse_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, 'lxml')

def basic_onpage_checks(url: str, html: str) -> Dict:
    soup = parse_html(html)
    title = (soup.title.text.strip() if soup.title else '')
    meta_desc = ''
    md = soup.find('meta', attrs={'name':'description'})
    if md and md.get('content'): meta_desc = md['content'].strip()
    h1s = [h.get_text(strip=True) for h in soup.find_all('h1')]
    imgs = soup.find_all('img')
    img_no_alt = sum(1 for i in imgs if not i.get('alt'))
    links = [a.get('href') for a in soup.find_all('a') if a.get('href')]
    a_internal = [l for l in links if l.startswith('/') or l.startswith('#') or l.startswith('./')]
    a_external = [l for l in links if l.startswith('http')]
    opengraph = bool(soup.find('meta', property=re.compile('^og:')))
    viewport = bool(soup.find('meta', attrs={'name':'viewport'}))
    return {
        'title': title, 'meta_desc': meta_desc, 'h1s': h1s,
        'img_no_alt': img_no_alt, 'img_total': len(imgs),
        'links_total': len(links), 'links_internal': len(a_internal), 'links_external': len(a_external),
        'opengraph': opengraph, 'viewport': viewport
    }
