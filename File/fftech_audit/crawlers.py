# fftech_audit/crawlers.py (v2.1 — robust URL handling)
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
# Friendlier UA; allow override via env
USER_AGENT = os.getenv(
    "CRAWL_UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 FFTechAI-AuditBot/2.1 (+https://fftech.ai)"
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

def _normalize_seed(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return "https://"
    # add scheme if missing
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url

def _probe_fallback(url: str) -> str:
    """Try https first; if it fails to connect quickly, fallback to http."""
    parsed = up.urlparse(url)
    if parsed.scheme == "https":
        origin = f"{parsed.scheme}://{parsed.netloc}"
        try:
            with httpx.Client(timeout=5.0, headers={"User-Agent": USER_AGENT}) as client:
                r = client.head(origin)
                if r.status_code >= 400:
                    # Some servers block HEAD; try GET
                    rg = client.get(origin)
                    if rg.status_code < 400:
                        return url
                else:
                    return url
        except Exception:
            # fallback to http
            return up.urlunparse(parsed._replace(scheme="http"))
    return url

def _same_host(u1: str, u2: str) -> bool:
    return up.urlparse(u1).netloc == up.urlparse(u2).netloc

def _normalize_url(base: str, href: str) -> Optional[str]:
    try:
        href = (href or "").strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            return None
        return up.urljoin(base, href)
    except Exception:
        return None

# ... (truncated 6200 characters; assume complete in local) ...

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
    )
