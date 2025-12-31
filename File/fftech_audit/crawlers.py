
# fftech_audit/crawlers.py (v2.2 — robust URL handling w/ 'haier' brand mapping)
import os
import re
import time
import urllib.parse as up
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple
from collections import deque, Counter
import httpx
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import urllib.robotparser as robotparser

MAX_PAGES = int(os.getenv("MAX_PAGES", "120"))
TIMEOUT = float(os.getenv("CRAWL_TIMEOUT", "15.0"))
MAX_LINK_CHECKS = int(os.getenv("MAX_LINK_CHECKS", "150"))
USER_AGENT = os.getenv(
    "CRAWL_UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 FFTechAI-AuditBot/2.2 (+https://fftech.ai)"
)

@dataclass
class PageInfo:
    url: str
    status: int
    content_type: str
    content_len: int
    response_ms: int
    headers: Dict[str, str]
    raw_html: str
    html_title: Optional[str] = None
    meta_desc: Optional[str] = None
    h1_count: int = 0
    canonical: Optional[str] = None
    meta_robots: Optional[str] = None
    links_internal: List[str] = field(default_factory=list)
    links_external: List[str] = field(default_factory=list)
    images: List[Dict] = field(default_factory=list)  # [{"src":..., "attrs":{...}}]
    images_missing_alt: int = 0
    og_tags_present: bool = False
    schema_present: bool = False
    hreflang: List[Tuple[str, str]] = field(default_factory=list)
    rel_prev: Optional[str] = None
    rel_next: Optional[str] = None
    scripts: int = 0
    stylesheets: int = 0
    scripts_src: List[str] = field(default_factory=list)
    stylesheets_href: List[str] = field(default_factory=list)
    dom_nodes_est: int = 0
    mixed_content_http: int = 0
    viewport_meta: bool = False
    depth: int = 0

@dataclass
class CrawlResult:
    seed: str
    pages: List[PageInfo]
    errors: List[str]
    status_counts: Counter
    internal_links: Set[str]
    external_links: Set[str]
    broken_links_internal: Set[str]
    broken_links_external: Set[str]
    robots_allowed: bool
    sitemap_urls: List[str]
    redirect_chains: List[List[str]] = field(default_factory=list)
    redirect_loops: List[List[str]] = field(default_factory=list)
    robots_blocked: List[str] = field(default_factory=list)

_BRAND_MAP = {
    # brand-friendly fallback for Pakistan market
    "haier": "https://www.haier.com.pk",
}

def _normalize_seed(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return _BRAND_MAP.get("haier", "https://www.haier.com.pk")

    # single-word brand -> mapped origin
    if "." not in url and "/" not in url:
        lower = url.lower()
        if lower in _BRAND_MAP:
            return _BRAND_MAP[lower]
        # generic heuristic: assume .com
        return "https://" + lower

    # add scheme if missing
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url

def _probe_fallback(url: str) -> str:
    """Try https first; fallback to http if origin blocks quick connects."""
    parsed = up.urlparse(url)
    if parsed.scheme == "https":
        origin = f"{parsed.scheme}://{parsed.netloc}"
        try:
            with httpx.Client(timeout=5.0, headers={"User-Agent": USER_AGENT}) as client:
                r = client.head(origin)
                if r.status_code >= 400:
                    rg = client.get(origin)
                    if 200 <= rg.status_code < 400:
                        return url
                else:
                    return url
        except Exception:
            return up.urlunparse(parsed._replace(scheme="http"))
    return url

def _same_host(u1: str, u2: str) -> bool:
    return up.urlparse(u1).netloc == up.urlparse(u2).netloc

def _normalize_url(base: str, href: str) -> Optional[str]:
    try:
        href = (href or "").strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            return None
        absolute = up.urljoin(base, href)
        parsed = up.urlparse(absolute)
        if not parsed.scheme.startswith("http"):
            return None
        return up.urlunparse(parsed._replace(fragment=""))
    except Exception:
        return None

def _fetch_robots(seed: str) -> robotparser.RobotFileParser:
    rp = robotparser.RobotFileParser()
    try:
        origin = f"{up.urlparse(seed).scheme}://{up.urlparse(seed).netloc}"
        robots_url = up.urljoin(origin, "/robots.txt")
        rp.set_url(robots_url)
        rp.read()
    except Exception:
        pass
    return rp

def _discover_sitemaps(seed: str) -> List[str]:
    urls = []
    try:
        origin = f"{up.urlparse(seed).scheme}://{up.urlparse(seed).netloc}"
        robots_txt = up.urljoin(origin, "/robots.txt")
        with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
            r = client.get(robots_txt)
            if r.status_code == 200:
                for line in r.text.splitlines():
                    if line.lower().startswith("sitemap:"):
                        urls.append(line.split(":", 1)[1].strip())
        candidate = up.urljoin(origin, "/sitemap.xml")
        with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
            r = client.get(candidate)
            if r.status_code == 200 and "xml" in r.headers.get("Content-Type", ""):
                urls.append(candidate)
    except Exception:
        pass
    return list(dict.fromkeys(urls))

def _parse_sitemap(url: str) -> List[str]:
    urls = []
    try:
        with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
            r = client.get(url)
            if r.status_code != 200:
                return urls
            root = ET.fromstring(r.text)
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            for loc in root.findall(".//sm:loc", ns):
                if loc.text:
                    urls.append(loc.text.strip())
    except Exception:
        pass
    return urls

def crawl_site(seed: str, max_pages: int = MAX_PAGES) -> CrawlResult:
    seed = _probe_fallback(_normalize_seed(seed))
    errors: List[str] = []
    pages: List[PageInfo] = []
    status_counts = Counter()
    internal_links: Set[str] = set()
    external_links: Set[str] = set()
    broken_internal: Set[str] = set()
    broken_external: Set[str] = set()
    redirect_chains: List[List[str]] = []
    redirect_loops: List[List[str]] = []
    robots_blocked: List[str] = []

    rp = _fetch_robots(seed)
    robots_allowed = rp.can_fetch(USER_AGENT, seed) if rp.default_entry is not None else True

    q = deque([(seed, 0)])
    seen: Set[str] = {seed}

    sitemap_urls = _discover_sitemaps(seed)
    for sm in list(sitemap_urls):
        for u in _parse_sitemap(sm):
            if _same_host(seed, u) and len(seen) < max_pages and u not in seen:
                seen.add(u)
                q.append((u, 0))

    soup_parser = "lxml"
    try:
        import lxml  # noqa
    except Exception:
        soup_parser = "html.parser"

    headers_common = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": os.getenv("ACCEPT_LANGUAGE", "en-US,en;q=0.8"),
    }

    def _track_redirects(history: List[httpx.Response]) -> None:
        if not history:
            return
        chain = [str(h.request.url) for h in history]
        if len(chain) >= 2:
            redirect_chains.append(chain)
            if chain[0] == chain[-1]:
                redirect_loops.append(chain)

    with httpx.Client(timeout=TIMEOUT, headers=headers_common, follow_redirects=True) as client:
        while q and len(pages) < max_pages:
            url, depth = q.popleft()
            try:
                if rp.default_entry is not None and not rp.can_fetch(USER_AGENT, url):
                    robots_blocked.append(url)
                    continue

                start = time.time()
                r = client.get(url)
                elapsed_ms = int((time.time() - start) * 1000)

                _track_redirects(r.history)

                status = r.status_code
                status_counts[status // 100 * 100] += 1
                ctype = r.headers.get("Content-Type", "")
                clen = int(r.headers.get("Content-Length") or len(r.content))

                pi = PageInfo(
                    url=url, status=status, content_type=ctype, content_len=clen,
                    response_ms=elapsed_ms, headers=dict(r.headers), raw_html=r.text, depth=depth
                )

                if "text/html" in ctype and r.text:
                    soup = BeautifulSoup(r.text, soup_parser)

                    # Content
                    pi.html_title = soup.title.string.strip() if soup.title and soup.title.string else None
                    desc_el = soup.find("meta", attrs={"name": "description"})
                    pi.meta_desc = (desc_el.get("content", "").strip() if desc_el else None)
                    pi.h1_count = len(soup.find_all("h1"))
                    can_el = soup.find("link", rel=lambda v: v and "canonical" in v.lower())
                    pi.canonical = (can_el.get("href") if can_el else None)
                    mr = soup.find("meta", attrs={"name": "robots"})
                    pi.meta_robots = (mr.get("content") if mr else None)

                    # Links + enqueue internal
                    for a in soup.find_all("a", href=True):
                        tgt = _normalize_url(url, a.get("href"))
                        if not tgt:
                            continue
                        if _same_host(seed, tgt):
                            pi.links_internal.append(tgt)
                            if tgt not in seen and len(seen) < max_pages:
                                seen.add(tgt)
                                q.append((tgt, depth + 1))
                            internal_links.add(tgt)
                        else:
                            pi.links_external.append(tgt)
                            external_links.add(tgt)

                    # Images list with attrs
                    missing = 0
                    img_list = []
                    for img in soup.find_all("img"):
                        alt = img.get("alt")
                        if not (alt and str(alt).strip()):
                            missing += 1
                        img_list.append({"src": img.get("src"), "attrs": img.attrs})
                    pi.images = img_list
                    pi.images_missing_alt = missing

                    # Open Graph & JSON-LD
                    pi.og_tags_present = len(soup.find_all("meta", property=re.compile(r"^og:"))) > 0
                    pi.schema_present = len(soup.find_all("script", type="application/ld+json")) > 0

                    # Hreflang
                    for ln in soup.find_all("link", attrs={"rel": "alternate"}):
                        if ln.get("hreflang") and ln.get("href"):
                            pi.hreflang.append((ln.get("hreflang"), ln.get("href")))

                    # Pagination
                    prev = soup.find("link", rel="prev")
                    next_ = soup.find("link", rel="next")
                    pi.rel_prev = prev.get("href") if prev else None
                    pi.rel_next = next_.get("href") if next_ else None

                    # Resources
                    pi.scripts = len(soup.find_all("script"))
                    pi.stylesheets = len(soup.find_all("link", rel=lambda v: v and "stylesheet" in v.lower()))
                    pi.scripts_src = [s.get("src") for s in soup.find_all("script", src=True)]
                    pi.stylesheets_href = [l.get("href") for l in soup.find_all("link", rel=lambda v: v and "stylesheet" in v.lower(), href=True)]
                    pi.dom_nodes_est = sum(1 for _ in soup.descendants if getattr(_, "name", None))

                    # Viewport meta
                    pi.viewport_meta = bool(soup.find("meta", attrs={"name": "viewport"}))

                    # Mixed content (HTTP resources on HTTPS pages)
                    pi.mixed_content_http = 0
                    if url.startswith("https://"):
                        for tag in soup.find_all(["img", "script", "link"], src=True):
                            src = tag.get("src")
                            if src and str(src).strip().startswith("http://"):
                                pi.mixed_content_http += 1
                        for tag in soup.find_all("link", href=True):
                            href = tag.get("href")
                            if href and str(href).strip().startswith("http://"):
                                pi.mixed_content_http += 1

                pages.append(pi)

            except Exception as e:
                errors.append(f"{url} -> {e}")

    # Broken-link sample checks (HEAD with fallback to GET)
    def _head_ok(u: str) -> bool:
        try:
            with httpx.Client(timeout=TIMEOUT, headers=headers_common, follow_redirects=True) as client:
                r = client.head(u)
                if r.status_code >= 400:
                    rg = client.get(u)
                    return 200 <= rg.status_code < 400
                return 200 <= r.status_code < 400
        except Exception:
            return False

    checks = 0
    for u in list(internal_links):
        if checks > MAX_LINK_CHECKS:
            break
        checks += 1
        if not _head_ok(u):
            broken_internal.add(u)
    for u in list(external_links):
        if checks > MAX_LINK_CHECKS:
            break
        checks += 1
        if not _head_ok(u):
            broken_external.add(u)

    return CrawlResult(
        seed=seed,
        pages=pages,
        errors=errors,
        status_counts=status_counts,
        internal_links=internal_links,
        external_links=external_links,
        broken_links_internal=broken_internal,
        broken_links_external=broken_external,
        robots_allowed=robots_allowed,
        sitemap_urls=sitemap_urls,
        redirect_chains=redirect_chains,
        redirect_loops=redirect_loops,
        robots_blocked=robots_blocked,
    )
