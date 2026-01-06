
from typing import Dict, Any, List, Tuple
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse
from html.parser import HTMLParser
import re
import ssl

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) FFTechAudit/1.0 Chrome/119.0 Safari/537.36'
ACCEPT_LANG = 'en-US,en;q=0.9'
TIMEOUT_S = 10

# Simple HTML parser to collect tags quickly
class TagCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: List[Tuple[str, Dict[str,str]]] = []
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag.lower(), {k.lower(): (v or '') for k, v in attrs}))

def _fetch(url: str) -> Tuple[int, bytes, Dict[str, str]]:
    """Fetch URL with robust headers; return status, body, headers."""
    req = Request(url, headers={
        'User-Agent': USER_AGENT,
        'Accept-Language': ACCEPT_LANG,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Connection': 'close',
    })
    # allow TLS without verification config changes (safer to verify, but sandbox may lack CA bundle)
    ctx = ssl.create_default_context()
    try:
        with urlopen(req, timeout=TIMEOUT_S, context=ctx) as resp:
            status = resp.getcode()
            headers = {k.lower(): v for k, v in resp.info().items()}
            data = resp.read() or b''
            return status, data, headers
    except HTTPError as e:
        return e.code, b'', {k.lower(): v for k, v in (e.headers or {}).items()}
    except URLError as e:
        return 0, b'', {'error': str(e)}
    except Exception as e:
        return 0, b'', {'error': str(e)}

def _get_text(data: bytes) -> str:
    try:
        text = data.decode('utf-8', errors='ignore')
        if not text:
            text = data.decode('latin-1', errors='ignore')
        return text
    except Exception:
        return ''

def _robots_allowed(base: str) -> bool:
    """Check robots.txt for a disallow all pattern."""
    p = urlparse(base)
    robots = f"{p.scheme}://{p.netloc}/robots.txt"
    status, body, _ = _fetch(robots)
    if status == 0:
        return True
    text = _get_text(body).lower()
    # crude check: disallow / for all user-agents
    if 'user-agent: *' in text and 'disallow: /' in text:
        return False
    return True

def _sitemap_present(base: str) -> bool:
    p = urlparse(base)
    for name in ('sitemap.xml', 'sitemap_index.xml'):
        url = f"{p.scheme}://{p.netloc}/{name}"
        status, _, _ = _fetch(url)
        if status and 200 <= status < 400:
            return True
    return False

def _score_bounds(val: int) -> int:
    return max(0, min(100, val))

def run_basic_checks(url: str) -> Dict[str, Any]:
    """
    World-class, dependency-free heuristics for Performance, Accessibility, SEO, Security, BestPractices.
    Returns: {
        'category_scores': { ... },
        'metrics': { ... },
        'top_issues': [ ... ]
    }
    """
    metrics: Dict[str, Any] = {}
    issues: List[str] = []
    cats: Dict[str, int] = {
        'Performance': 60,
        'Accessibility': 60,
        'SEO': 60,
        'Security': 60,
        'BestPractices': 60,
    }

    status, body, headers = _fetch(url)
    metrics['status_code'] = status
    metrics['content_length'] = len(body)
    metrics['content_encoding'] = headers.get('content-encoding', '')
    metrics['cache_control'] = headers.get('cache-control', '')
    metrics['hsts'] = headers.get('strict-transport-security', '')
    metrics['xcto'] = headers.get('x-content-type-options', '')
    metrics['xfo'] = headers.get('x-frame-options', '')
    metrics['csp'] = headers.get('content-security-policy', '')
    metrics['set_cookie'] = headers.get('set-cookie', '')

    text = _get_text(body)

    # Parse HTML for structure
    collector = TagCollector()
    try:
        collector.feed(text)
    except Exception:
        pass

    # Quick helpers from parsed tags
    def tags(name: str):
        return [a for t, a in collector.tags if t == name]

    titles = tags('title')
    title_text = ''
    if titles:
        # Rough regex fallback
        m = re.search(r'<title>(.*?)</title>', text, re.IGNORECASE|re.DOTALL)
        title_text = (m.group(1).strip() if m else '')
    metrics['title'] = title_text
    metrics['title_length'] = len(title_text)

    metas = tags('meta')
    meta_desc = ''
    meta_robots = ''
    for a in metas:
        n = a.get('name', '')
        if n == 'description' or a.get('property', '') == 'og:description':
            meta_desc = a.get('content', '')
        if n == 'robots':
            meta_robots = a.get('content', '')
    metrics['meta_description_length'] = len(meta_desc)
    metrics['meta_robots'] = meta_robots

    canonicals = [a.get('href','') for a in tags('link') if a.get('rel','') == 'canonical']
    metrics['canonical_present'] = bool(canonicals and canonicals[0])

    h1s = tags('h1')
    metrics['h1_count'] = len(h1s)

    imgs = tags('img')
    img_count = len(imgs)
    img_missing_alt = sum(1 for a in imgs if not a.get('alt'))
    metrics['image_count'] = img_count
    metrics['images_without_alt'] = img_missing_alt

    has_lang = any('lang' in a for t, a in collector.tags if t == 'html')
    has_viewport = any(a.get('name','') == 'viewport' for a in metas)
    metrics['html_lang_present'] = has_lang
    metrics['viewport_present'] = has_viewport

    # Robots & sitemap
    robots_ok = _robots_allowed(url)
    metrics['robots_allowed'] = robots_ok
    sitemap_ok = _sitemap_present(url)
    metrics['sitemap_present'] = sitemap_ok

    # Security heuristics
    parsed = urlparse(url)
    https = parsed.scheme.lower() == 'https'
    metrics['has_https'] = https

    # ---------- Scoring ----------
    # Performance: content length, compression, caching
    perf = 100
    size = metrics['content_length']
    if size == 0:
        perf -= 30; issues.append('No content received; check availability and payload.')
    elif size > 150_000:  # 150 KB
        perf -= min(50, (size - 150_000) // 20_000)
    if metrics['content_encoding'] not in ('gzip', 'br', 'deflate'):
        perf -= 10; issues.append('Response not compressed (gzip/br).')
    if not metrics['cache_control']:
        perf -= 10; issues.append('Missing Cache-Control headers.')
    cats['Performance'] = _score_bounds(perf)

    # Accessibility: alt text, viewport, lang, heading presence
    acc = 100
    if img_missing_alt > 0:
        acc -= min(30, img_missing_alt * 2)
        issues.append(f"{img_missing_alt} <img> without alt attribute.")
    if not has_viewport:
        acc -= 10; issues.append('No mobile viewport meta.')
    if not has_lang:
        acc -= 10; issues.append('<html lang> missing for language semantics.')
    if metrics['h1_count'] == 0:
        acc -= 10; issues.append('Missing <h1> heading.')
    cats['Accessibility'] = _score_bounds(acc)

    # SEO: title, description, canonical, robots/sitemap
    seo = 100
    tl = metrics['title_length']
    if tl == 0:
        seo -= 20; issues.append('Missing <title> tag.')
    elif tl < 10 or tl > 65:
        seo -= 10; issues.append('Title length suboptimal (10–65 chars).')
    mdl = metrics['meta_description_length']
    if mdl == 0:
        seo -= 15; issues.append('Missing meta description.')
    elif mdl < 50 or mdl > 160:
        seo -= 5; issues.append('Meta description length suboptimal (50–160 chars).')
    if not metrics['canonical_present']:
        seo -= 10; issues.append('Missing canonical link.')
    if 'noindex' in (metrics['meta_robots'] or '').lower():
        seo -= 20; issues.append('Meta robots set to noindex.')
    if not robots_ok:
        seo -= 20; issues.append('robots.txt disallows all (User-agent: * / Disallow: /).')
    if not sitemap_ok:
        seo -= 5; issues.append('No sitemap.xml discovered.')
    cats['SEO'] = _score_bounds(seo)

    # Security: HTTPS, HSTS, headers
    sec = 100
    if not https:
        sec -= 25; issues.append('Site not served over HTTPS.')
    if not metrics['hsts']:
        sec -= 10; issues.append('Missing Strict-Transport-Security (HSTS).')
    if (metrics['xcto'] or '').lower() != 'nosniff':
        sec -= 10; issues.append('Missing X-Content-Type-Options: nosniff.')
    if not metrics['xfo']:
        sec -= 5; issues.append('Missing X-Frame-Options (clickjacking risk).')
    if not metrics['csp']:
        sec -= 10; issues.append('Missing Content-Security-Policy.')
    # Basic cookie flags heuristic
    sc = metrics['set_cookie'] or ''
    if sc and ('httponly' not in sc.lower() or 'secure' not in sc.lower()):
        sec -= 5; issues.append('Cookies missing Secure/HttpOnly flags.')
    cats['Security'] = _score_bounds(sec)

    # Best Practices: OG tags, favicon, semantic sections
    bp = 100
    og_title = any(a.get('property','') == 'og:title' for a in metas)
    og_image = any(a.get('property','') == 'og:image' for a in metas)
    if not og_title or not og_image:
        bp -= 5; issues.append('Missing OpenGraph tags (og:title/og:image).')
    has_favicon = any(a.get('rel','') == 'icon' for a in tags('link'))
    if not has_favicon:
        bp -= 3; issues.append('No favicon link found.')
    has_main = any(t == 'main' for t, _ in collector.tags)
    has_nav = any(t == 'nav' for t, _ in collector.tags)
    if not has_main:
        bp -= 3; issues.append('No <main> landmark found.')
    if not has_nav:
        bp -= 2; issues.append('No <nav> landmark found.')
    cats['BestPractices'] = _score_bounds(bp)

    # If status indicates failure, soften scores but keep baseline
    if status == 0 or status >= 400:
        issues.append(f"HTTP status {status} detected; using heuristic baseline.")
        # reduce Performance/SEO a bit if fetch failed
        cats['Performance'] = max(30, cats['Performance'] - 20)
        cats['SEO'] = max(30, cats['SEO'] - 15)

    return {
        'category_scores': cats,
        'metrics': metrics,
        'top_issues': issues,
    }
