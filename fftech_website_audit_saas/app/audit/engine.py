import time
from typing import Dict, List, Tuple
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

HEADERS = {"User-Agent": "FFTechAuditBot/1.1 (+https://fftech.example)"}
TIMEOUT = 10

# Utility fetch with robust timing

def _fetch(url: str) -> Tuple[requests.Response, float]:
    start = time.time()
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    ttfb = resp.elapsed.total_seconds() or (time.time() - start)
    return resp, ttfb

# Helpers

def _is_https(url: str) -> bool:
    return url.lower().startswith('https://')


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ''

# Scoring helpers

def _score_performance(ttfb: float, size_kb: float, reqs: int, compressed: bool, cache_hdrs: bool, status_ok: bool) -> int:
    score = 100
    if not status_ok:
        return 5
    # TTFB impact
    if ttfb > 2.5: score -= 30
    elif ttfb > 1.8: score -= 20
    elif ttfb > 1.2: score -= 12
    elif ttfb > 0.8: score -= 6
    # size impact (HTML only)
    if size_kb > 2500: score -= 30
    elif size_kb > 1500: score -= 18
    elif size_kb > 800: score -= 10
    # requests impact
    if reqs > 120: score -= 25
    elif reqs > 80: score -= 15
    elif reqs > 40: score -= 8
    # compression & cache
    if compressed: score += 6
    if cache_hdrs: score += 4
    return max(0, min(100, score))


def _score_seo(title: str, has_desc: bool, h1_ok: bool, canonical_ok: bool, ld_json: bool, robots_meta: bool) -> int:
    score = 45
    if title and 10 <= len(title) <= 60: score += 20
    elif title: score += 10
    if has_desc: score += 15
    if h1_ok: score += 10
    if canonical_ok: score += 6
    if ld_json: score += 8  # structured data present
    if robots_meta: score += 6  # indexable tags present
    return max(0, min(100, score))


def _score_accessibility(imgs: int, imgs_with_alt: int, has_lang: bool, has_viewport: bool, labels_ratio: float) -> int:
    score = 45
    if imgs > 0:
        alt_ratio = imgs_with_alt / max(1, imgs)
        if alt_ratio >= 0.95: score += 25
        elif alt_ratio >= 0.8: score += 18
        elif alt_ratio >= 0.6: score += 12
        elif alt_ratio >= 0.4: score += 6
    if has_lang: score += 10
    if has_viewport: score += 6
    if labels_ratio >= 0.7: score += 8
    elif labels_ratio >= 0.5: score += 4
    return max(0, min(100, score))


def _score_best_practices(https_ok: bool, uses_https_assets: bool, js_count: int, css_count: int, cdn_hint: bool, mixed_content: bool) -> int:
    score = 45
    if https_ok: score += 20
    if uses_https_assets: score += 10
    if js_count <= 20: score += 8
    if css_count <= 8: score += 8
    if cdn_hint: score += 6
    if mixed_content: score -= 10
    return max(0, min(100, score))


def _score_security(headers: Dict[str, str], https_ok: bool) -> int:
    score = 40
    h = {k.lower(): v for k, v in headers.items()}
    if 'strict-transport-security' in h: score += 15
    if 'content-security-policy' in h: score += 20
    if 'x-frame-options' in h: score += 10
    if 'x-content-type-options' in h: score += 10
    if https_ok: score += 5
    return max(0, min(100, score))

# Main audit function

def run_basic_checks(url: str) -> Dict:
    try:
        resp, ttfb = _fetch(url)
    except Exception as e:
        return {
            "category_scores": {"Performance": 0, "SEO": 0, "Accessibility": 0, "Best Practices": 0, "Security": 0},
            "metrics": [("Error", str(e))],
            "top_issues": ["Site unreachable or timed out."]
        }

    status_ok = (200 <= resp.status_code < 400)
    html = resp.text
    size_kb = len(resp.content) / 1024.0
    soup = BeautifulSoup(html, 'html.parser')

    # Resource counts
    imgs = soup.find_all('img'); imgs_with_alt = [i for i in imgs if i.get('alt')]
    scripts = soup.find_all('script')
    links = soup.find_all('link')
    stylesheets = [l for l in links if 'stylesheet' in (l.get('rel') or [])]

    # SEO
    title_tag = soup.find('title'); title = title_tag.text.strip() if title_tag else ''
    desc = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
    h1 = soup.find('h1')
    canonical = soup.find('link', rel='canonical')
    ld_json = bool(soup.find('script', attrs={'type': 'application/ld+json'}))
    robots_meta = not soup.find('meta', attrs={'name': 'robots', 'content': lambda c: c and 'noindex' in c.lower()})

    # Accessibility / Best practices
    html_tag = soup.find('html'); has_lang = bool(html_tag and html_tag.get('lang'))
    viewport = soup.find('meta', attrs={'name': 'viewport'})
    https_ok = _is_https(url)

    # Asset protocols
    asset_urls = [a.get('src') for a in scripts if a.get('src')] + [l.get('href') for l in links if l.get('href')]
    https_assets = [u for u in asset_urls if u and u.lower().startswith('https://')]
    mixed_content = any(u and u.lower().startswith('http://') for u in asset_urls) if https_ok else False

    # Compression & caching
    enc = (resp.headers.get('content-encoding') or '').lower()
    compressed = ('gzip' in enc) or ('br' in enc)
    cache_hdrs = bool(resp.headers.get('cache-control') or resp.headers.get('etag'))

    # CDN hint
    server_hdr = (resp.headers.get('server') or '').lower()
    cdn_hint = any(k in server_hdr for k in ['cloudflare', 'akamai', 'fastly', 'cdn']) or any('cdn' in (u or '').lower() for u in asset_urls)

    # Labels ratio
    inputs = soup.find_all('input')
    labels = soup.find_all('label')
    labels_ratio = min(1.0, len(labels)/max(1, len(inputs))) if inputs else 1.0

    # Scores
    perf_score = _score_performance(ttfb, size_kb, len(scripts) + len(links) + len(imgs), compressed, cache_hdrs, status_ok)
    seo_score = _score_seo(title, bool(desc), bool(h1), bool(canonical), ld_json, robots_meta)
    acc_score = _score_accessibility(len(imgs), len(imgs_with_alt), has_lang, bool(viewport), labels_ratio)
    bp_score  = _score_best_practices(https_ok, len(https_assets) >= max(1, len(asset_urls)) * 0.8 if asset_urls else https_ok, len(scripts), len(stylesheets), cdn_hint, mixed_content)
    sec_score = _score_security(resp.headers, https_ok)

    categories = {
        "Performance": perf_score,
        "SEO": seo_score,
        "Accessibility": acc_score,
        "Best Practices": bp_score,
        "Security": sec_score
    }

    metrics = [
        ("Status", str(resp.status_code)),
        ("TTFB", f"{ttfb:.2f}s"),
        ("HTML size", f"{size_kb:.0f} KB"),
        ("Resources", f"img:{len(imgs)} • js:{len(scripts)} • css:{len(stylesheets)}"),
        ("Title length", str(len(title))),
        ("Images w/ alt", f"{len(imgs_with_alt)}/{len(imgs)}"),
        ("Compression", enc or 'none'),
        ("Caching", 'yes' if cache_hdrs else 'no'),
        ("HTTPS", 'yes' if https_ok else 'no'),
        ("Mixed content", 'yes' if mixed_content else 'no'),
        ("CDN hint", 'yes' if cdn_hint else 'no'),
        ("Security headers", ", ".join([k for k in resp.headers.keys() if k.lower() in ['strict-transport-security','content-security-policy','x-frame-options','x-content-type-options']]) or 'none')
    ]

    issues = []
    if not status_ok: issues.append("Check HTTP status and redirects")
    if ttfb > 1.5: issues.append("Reduce server response time (TTFB)")
    if size_kb > 1500: issues.append("Compress assets and enable caching")
    if not desc: issues.append("Add meta description")
    if not h1: issues.append("Add a primary H1 heading")
    if len(imgs) and len(imgs_with_alt) < len(imgs): issues.append("Add alt text to images")
    if https_ok and mixed_content: issues.append("Remove mixed content (http assets on https page)")
    if 'content-security-policy' not in {k.lower(): v for k, v in resp.headers.items()}: issues.append("Set Content-Security-Policy header")

    return {
        "category_scores": categories,
        "metrics": metrics,
        "top_issues": issues[:6]
    }
