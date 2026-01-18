
from urllib.parse import urlparse, urljoin

def normalize_url(url: str) -> str:
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"

def is_same_domain(base: str, other: str) -> bool:
    return urlparse(base).netloc == urlparse(other).netloc

def join_url(base: str, path: str) -> str:
    return urljoin(base, path)
