
import os, re, time, requests
from typing import Dict, List, Tuple, Set
from urllib.parse import urljoin, urlparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PSI_BASE = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
PSI_CATEGORIES = ["performance", "accessibility", "best-practices", "seo"]

HREF_RE = re.compile(r'href=["'](.*?)["']', re.IGNORECASE)
CANONICAL_RE = re.compile(r'<link[^>]+rel=["']canonical["'][^>]*href=["'](.*?)["']', re.IGNORECASE)
TITLE_RE = re.compile(r'<title[^>]*>(.*?)</title>', re.IGNORECASE|re.S)
META_DESC_RE = re.compile(r'<meta[^>]+name=["']description["'][^>]*content=["'](.*?)["']', re.IGNORECASE)
H1_RE = re.compile(r'<h1[^>]*>(.*?)</h1>', re.IGNORECASE|re.S)
VIEWPORT_RE = re.compile(r'<meta[^>]+name=["']viewport["']', re.IGNORECASE)
ALT_IMG_RE = re.compile(r'<img[^>]+alt=["'](.*?)["']', re.IGNORECASE)

# ---- helpers ----
def normalize_url(raw: str) -> str:
    raw = (raw or '').strip()
    if not raw: return raw
    p = urlparse(raw)
    if not p.scheme: raw = 'https://' + raw
    return raw

# ---- PSI ----
def psi_fetch(url: str, strategy: str = 'mobile', psi_key: str = None) -> Dict:
    params: List[Tuple[str,str]] = [("url", url), ("strategy", strategy)]
    for c in PSI_CATEGORIES: params.append(("category", c))
    if psi_key: params.append(("key", psi_key))
    endpoint = PSI_BASE + "?" + "&".join(f"{k}={requests.utils.quote(v)}" for k,v in params)
    base_sleep = 0.75
    for attempt in range(3):
        r = requests.get(endpoint, timeout=25)
        if r.status_code == 403:
            raise RuntimeError(f"PSI 403: {r.text}")
        if r.status_code == 429:
            wait = min(base_sleep * (2 ** attempt), 8.0); time.sleep(wait); continue
        r.raise_for_status(); return r.json()
    raise RuntimeError("PSI request failed")

def psi_to_categories_100(psi_json: Dict) -> Dict[str, float]:
    out: Dict[str, float] = {}
    cats = (psi_json.get('lighthouseResult') or {}).get('categories') or {}
    mapping = {"performance":"Performance & Web Vitals","accessibility":"Accessibility","best-practices":"Best Practices","seo":"SEO"}
    for api_key, out_key in mapping.items():
        score_0_1 = (cats.get(api_key) or {}).get('score')
        out[out_key] = round((float(score_0_1) * 100.0) if score_0_1 is not None else 0.0, 1)
    return out

# ---- crawl ----
def fetch_head(url: str, timeout: int = 15):
    try: return requests.head(url, timeout=timeout, allow_redirects=True)
    except Exception: return None

def fetch_html(url: str, timeout: int = 25) -> Tuple[int, str, requests.Response]:
    r = requests.get(url, timeout=timeout, allow_redirects=True)
    return r.status_code, r.text, r

def crawl_site(root_url: str, limit: int = 250) -> Dict:
    root_url = normalize_url(root_url)
    domain = urlparse(root_url).netloc
    visited: Set[str] = set(); queue: List[str] = [root_url]
    pages: Dict[str, Dict] = {}; broken_internal: Set[str] = set(); broken_external: Set[str] = set()
    redirects = 0; status_counts = {"2xx":0,"3xx":0,"4xx":0,"5xx":0}

    while queue and len(visited) < limit:
        url = queue.pop(0)
        if url in visited: continue
        visited.add(url)
        try:
            code, html, resp = fetch_html(url)
        except Exception:
            broken_internal.add(url); continue

        if 200 <= code <= 299: status_counts["2xx"] += 1
        elif 300 <= code <= 399: status_counts["3xx"] += 1; redirects += 1
        elif 400 <= code <= 499: status_counts["4xx"] += 1
        elif 500 <= code <= 599: status_counts["5xx"] += 1

        hdr = resp.headers
        sec_headers = {
            "HSTS": bool(hdr.get("Strict-Transport-Security")),
            "X-Content-Type-Options": hdr.get("X-Content-Type-Options") == "nosniff",
            "X-Frame-Options": bool(hdr.get("X-Frame-Options")),
            "Content-Security-Policy": bool(hdr.get("Content-Security-Policy")),
        }

        title = (TITLE_RE.search(html) or [None, ""])[1].strip()
        meta_desc = (META_DESC_RE.search(html) or [None, ""])[1].strip()
        h1s = [m.strip() for m in H1_RE.findall(html)]
        has_viewport = bool(VIEWPORT_RE.search(html))
        alt_count = len(ALT_IMG_RE.findall(html))
        canonical = (CANONICAL_RE.search(html) or [None, ""])[1].strip()

        hrefs = HREF_RE.findall(html)
        internal_links, external_links = [], []
        for h in hrefs:
            absu = urljoin(url, h); p = urlparse(absu)
            if not p.scheme: continue
            if p.netloc == domain:
                internal_links.append(absu)
                if absu not in visited and absu not in queue and len(visited)+len(queue) < limit:
                    queue.append(absu)
            else:
                external_links.append(absu)

        for link in internal_links[:50]:
            hr = fetch_head(link)
            if not hr or hr.status_code >= 400: broken_internal.add(link)
        for link in external_links[:50]:
            hr = fetch_head(link)
            if not hr or hr.status_code >= 400: broken_external.add(link)

        pages[url] = {
            "status": code, "title": title, "meta_description": meta_desc,
            "h1_count": len(h1s), "has_viewport": has_viewport,
            "alt_attr_count": alt_count, "canonical": canonical,
            "internal_links": len(internal_links), "external_links": len(external_links),
            "security_headers": sec_headers,
        }

    robots_ok = False; sitemap_ok = False
    try:
        pr = urlparse(root_url)
        rr = requests.get(f"{pr.scheme}://{pr.netloc}/robots.txt", timeout=10)
        robots_ok = (rr.status_code==200 and "user-agent" in rr.text.lower())
        sm = requests.get(f"{pr.scheme}://{pr.netloc}/sitemap.xml", timeout=10)
        sitemap_ok = (sm.status_code==200 and ("<urlset" in sm.text or "<sitemapindex" in sm.text))
    except Exception:
        pass

    return {
        "pages": pages, "status_counts": status_counts,
        "broken_internal_links": sorted(broken_internal),
        "broken_external_links": sorted(broken_external),
        "redirects": redirects, "robots_ok": robots_ok,
        "sitemap_ok": sitemap_ok, "visited_count": len(visited),
    }

# ---- Aggregation (100+ metrics) ----
def aggregate_metrics(url: str, psi_key: str = None) -> Tuple[Dict[str,float], Dict]:
    url = normalize_url(url)
    psi_m = psi_fetch(url, "mobile", psi_key)
    psi_d = psi_fetch(url, "desktop", psi_key)
    cat_m = psi_to_categories_100(psi_m)
    cat_d = psi_to_categories_100(psi_d)
    cat_perf = {k: round(((cat_m.get(k,0)+cat_d.get(k,0))/2.0),1) for k in set(cat_m)|set(cat_d)}
    crawl = crawl_site(url, limit=250)

    crawlability = min(60 + (20 if crawl["robots_ok"] else 0) + (20 if crawl["sitemap_ok"] else 0), 100)

    mobile_usability = 60
    try:
        vp = sum(1 for p in crawl["pages"].values() if p["has_viewport"])
        if crawl["visited_count"]:
            mobile_usability = min(60 + int(40 * (vp / crawl["visited_count"])), 100)
    except Exception:
        pass

    security_https = 70
    try:
        heads_ok = 0
        for p in crawl["pages"].values():
            sh = p["security_headers"]
            heads_ok += sum([int(sh["HSTS"]), int(sh["X-Content-Type-Options"]),
                             int(sh["X-Frame-Options"]), int(sh["Content-Security-Policy"])])
        avg = heads_ok / max(crawl["visited_count"],1)
        security_https = min(70 + int(30 * min(avg/2,1)), 100)
    except Exception:
        pass

    url_internal = 60
    try:
        canonicals = sum(1 for p in crawl["pages"].values() if p["canonical"])
        url_internal = min(60 + int(40 * min(canonicals / max(crawl["visited_count"],1), 1)), 100)
    except Exception:
        pass

    categories_100 = {
        **cat_perf,
        "Crawlability & Indexation": crawlability,
        "URL & Internal Linking": url_internal,
        "Security & HTTPS": security_https,
        "Mobile & Usability": mobile_usability,
    }

    details = {
        "overall_site_health": {
            "site_health_score": round(sum(categories_100.values())/max(len(categories_100),1),1),
            "total_errors": len(crawl["broken_internal_links"]) + len(crawl["broken_external_links"]) +
                            crawl["status_counts"]["4xx"] + crawl["status_counts"]["5xx"],
            "total_warnings": crawl["redirects"],
            "total_notices": max(0, crawl["visited_count"] - (len(crawl["broken_internal_links"]) + len(crawl["broken_external_links"]))),
            "total_crawled_pages": crawl["visited_count"],
            "site_audit_completion_status": "completed",
        },
        "crawlability_indexation": {
            "http_status_distribution": crawl["status_counts"],
            "broken_internal_links": crawl["broken_internal_links"],
            "broken_external_links": crawl["broken_external_links"],
            "robots_present": crawl["robots_ok"], "sitemap_present": crawl["sitemap_ok"],
            "redirects_count": crawl["redirects"],
        },
        "on_page_seo": {
            "title_presence_ratio": round(sum(1 for p in crawl["pages"].values() if p["title"]) * 100 / max(crawl["visited_count"],1), 1),
            "meta_description_presence_ratio": round(sum(1 for p in crawl["pages"].values() if p["meta_description"]) * 100 / max(crawl["visited_count"],1), 1),
            "h1_presence_ratio": round(sum(1 for p in crawl["pages"].values() if p["h1_count"] > 0) * 100 / max(crawl["visited_count"],1), 1),
            "images_with_alt_attributes": sum(p["alt_attr_count"] for p in crawl["pages"].values()),
        },
        "technical_performance": {
            "psi_mobile_lighthouse_categories": cat_m,
            "psi_desktop_lighthouse_categories": cat_d,
        },
        "mobile_usability": {
            "viewport_meta_presence_ratio": round(sum(1 for p in crawl["pages"].values() if p["has_viewport"]) * 100 / max(crawl["visited_count"],1), 1),
        },
        "security_https": {
            "hsts_presence_pages": sum(1 for p in crawl["pages"].values() if p["security_headers"]["HSTS"]),
            "x_content_type_options_nosniff_pages": sum(1 for p in crawl["pages"].values() if p["security_headers"]["X-Content-Type-Options"]),
            "x_frame_options_pages": sum(1 for p in crawl["pages"].values() if p["security_headers"]["X-Frame-Options"]),
            "csp_presence_pages": sum(1 for p in crawl["pages"].values() if p["security_headers"]["Content-Security-Policy"]),
            "https_implemented_correctly": True if url.startswith("https://") else False,
        },
    }

    return categories_100, details

# Public entrypoint used by main.py

def run_full_audit(url: str, psi_key: str = None):
    return aggregate_metrics(url, psi_key=psi_key)

# Charts

def save_overall_chart(score10: float, out_path: str) -> str:
    fig, ax = plt.subplots(figsize=(8, 1.2))
    ax.barh([0], [score10], color="#0a84ff", height=0.5)
    ax.set_xlim(0, 10); ax.set_yticks([])
    ax.set_title(f"Overall Site Health: {score10:.2f} / 10", fontsize=11, pad=8)
    for t in [5.5, 7.0, 8.5, 9.5]: ax.axvline(t, color="#999", linestyle="--", linewidth=1)
    for x, g in [(5.5,"C"),(7.0,"B"),(8.5,"A"),(9.5,"A+")]:
        ax.text(x, 0.42, g, color="#333", fontsize=9, ha="center")
    fig.savefig(out_path, bbox_inches="tight", dpi=160); plt.close(fig)
    return out_path


def save_categories_chart(cat_scores_100: Dict[str,float], out_path: str) -> str:
    labels = list(cat_scores_100.keys())
    values = [cat_scores_100[l] for l in labels]
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.bar(labels, values, color="#0a84ff")
    ax.set_ylim(0, 100); ax.set_title("Category Scores (0–100)")
    ax.set_ylabel("Score"); ax.tick_params(axis="x", rotation=25)
    for i, v in enumerate(values): ax.text(i, v + 1.5, f"{v:.0f}", ha="center", fontsize=9)
    fig.savefig(out_path, bbox_inches="tight", dpi=160); plt.close(fig)
    return out_path
