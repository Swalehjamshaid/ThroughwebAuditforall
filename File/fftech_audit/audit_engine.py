
# fftech_audit/audit_engine.py
from urllib.parse import urlparse, urljoin
from typing import Dict, Any, Tuple, List
import re, time
try:
    import requests
except Exception:
    requests = None
import urllib.request
import ssl

# Minimal descriptors used by results table
METRIC_DESCRIPTORS: Dict[int, Dict[str, str]] = {
    10: {"name": "HTTPS Enabled", "category": "Security"},
    20: {"name": "TTFB (ms)", "category": "Performance"},
    21: {"name": "Page Size (KB)", "category": "Performance"},
    30: {"name": "Has Title Tag", "category": "SEO"},
    31: {"name": "Has Meta Description", "category": "SEO"},
    40: {"name": "Has Viewport Meta", "category": "Mobile"},
    50: {"name": "Has H1", "category": "Content"},
    51: {"name": "Images Have Alt", "category": "Content"},
    100: {"name": "Errors", "category": "Summary"},
    101: {"name": "Warnings", "category": "Summary"},
    102: {"name": "Notices", "category": "Summary"},
}

def canonical_origin(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme or 'https'
    host = parsed.netloc or parsed.path.split('/')[0]
    return f"{scheme}://{host}".lower()

USER_AGENT = 'FFTech-AuditBot/1.0 (+https://fftech.ai)'

class FetchResult:
    def __init__(self, status: int, headers: Dict[str,str], content: bytes, elapsed_ms: int, url: str):
        self.status = status
        self.headers = headers
        self.content = content
        self.elapsed_ms = elapsed_ms
        self.url = url

def fetch(url: str, timeout: float = 10.0) -> FetchResult:
    start = time.time()
    headers = {}
    content = b''
    status = 0
    final_url = url
    if requests:
        try:
            r = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=timeout, allow_redirects=True)
            status = r.status_code
            headers = {k.lower(): v for k, v in r.headers.items()}
            content = r.content or b''
            final_url = str(r.url)
        except Exception:
            pass
    if status == 0:
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                status = getattr(resp, 'status', 200)
                headers = {k.lower(): v for k, v in resp.getheaders()}
                content = resp.read() or b''
                final_url = resp.geturl()
        except Exception:
            status = 0
    elapsed_ms = int((time.time() - start) * 1000)
    return FetchResult(status, headers, content, elapsed_ms, final_url)

def head_exists(base: str, path: str, timeout: float = 5.0) -> bool:
    url = urljoin(base, path)
    if requests:
        try:
            r = requests.head(url, headers={'User-Agent': USER_AGENT}, timeout=timeout, allow_redirects=True)
            return r.status_code < 400
        except Exception:
            pass
    try:
        req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': USER_AGENT})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx, timeout=timeout):
            return True
    except Exception:
        return False

class AuditEngine:
    def __init__(self, url: str):
        self.url = url

    def compute_metrics(self) -> Dict[int, Dict[str, Any]]:
        target_url = self.url
        r = fetch(target_url)
        headers = r.headers
        content = r.content
        html_text = content.decode('utf-8', errors='ignore') if content else ''

        # Security
        sec_https = target_url.startswith('https://')

        # Performance
        ttfb_ms = r.elapsed_ms
        size_kb = int(len(content)/1024) if content else 0

        # SEO
        has_title = bool(re.search(r'<title\b[^>]*>.*?</title>', html_text, re.I | re.S))
        has_desc  = bool(re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']', html_text, re.I))
        origin = canonical_origin(target_url)
        # Still useful origin-level checks
        # has_sitemap = head_exists(origin, '/sitemap.xml')
        # has_robots  = head_exists(origin, '/robots.txt')

        # Mobile
        viewport   = bool(re.search(r'<meta[^>]*name=["\']viewport["\'][^>]*>', html_text, re.I))

        # Content
        has_h1 = bool(re.search(r'<h1\b', html_text, re.I))
        alt_ok = bool(re.search(r'<img\b[^>]*\salt=["\']', html_text, re.I))

        metrics = {
            10: {"value": sec_https},
            20: {"value": ttfb_ms},
            21: {"value": size_kb},
            30: {"value": has_title},
            31: {"value": has_desc},
            40: {"value": viewport},
            50: {"value": has_h1},
            51: {"value": alt_ok},
            100: {"value": 0},
            101: {"value": int(not viewport) + int(not has_title) + int(not has_desc)},
            102: {"value": 0},
        }
        return metrics
