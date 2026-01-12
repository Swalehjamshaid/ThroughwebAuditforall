# app/audit/utils.py
from urllib.parse import urlparse

def normalize_url(raw: str) -> str:
    if not raw:
        return raw
    s = raw.strip()
    if not s:
        return s
    p = urlparse(s)
    if not p.scheme:
        s = "https://" + s
        p = urlparse(s)
    if not p.netloc and p.path:
        s = f"{p.scheme}://{p.path}"
        p = urlparse(s)
    path = p.path or "/"
    return f"{p.scheme}://{p.netloc}{path}"

def url_variants(u: str) -> list:
    p = urlparse(u)
    host = p.netloc
    path = p.path or "/"
    scheme = p.scheme
    candidates = [f"{scheme}://{host}{path}"]
    if host.startswith("www."):
        candidates.append(f"{scheme}://{host[4:]}{path}")
    else:
        candidates.append(f"{scheme}://www.{host}{path}")
    candidates.append(f"http://{host}{path}")
    if host.startswith("www."):
        candidates.append(f"http://{host[4:]}{path}")
    else:
        candidates.append(f"http://www.{host}{path}")
    if not path.endswith("/"):
        candidates.append(f"{scheme}://{host}{path}/")
    seen, ordered = set(), []
    for c in candidates:
        if c not in seen:
            ordered.append(c); seen.add(c)
    return ordered
