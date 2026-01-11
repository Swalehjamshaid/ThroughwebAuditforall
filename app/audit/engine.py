from typing import Dict, Any
import re

try:
    import requests
    from bs4 import BeautifulSoup
except Exception:
    requests = None
    BeautifulSoup = None

def _safe_get(url: str) -> bytes:
    if requests is None:
        raise RuntimeError('requests package not installed.')
    resp = requests.get(url, timeout=15, headers={'User-Agent': 'FFTechAudit/1.0'})
    resp.raise_for_status()
    return resp.content

def run_basic_checks(url: str) -> Dict[str, Any]:
    html = _safe_get(url)
    size_kb = len(html) / 1024.0
    soup = BeautifulSoup(html, 'html.parser') if BeautifulSoup else None
    external_assets = 0
    if soup:
        external_assets += len(soup.find_all('script', src=True))
        external_assets += len(soup.find_all('link', href=True))
        external_assets += len(soup.find_all('img', src=True))
    perf_score = max(0, min(100, int(100 - (size_kb/200.0)*100 - external_assets*2)))
    title_ok = bool(soup.title and soup.title.string and len(soup.title.string.strip()) >= 10) if soup else False
    meta_desc = soup.find('meta', attrs={'name': 'description'}) if soup else None
    h1_ok = bool(soup.find('h1')) if soup else False
    canonical_ok = bool(soup.find('link', rel=re.compile('canonical', re.I))) if soup else False
    seo_hits = sum([title_ok, bool(meta_desc), h1_ok, canonical_ok])
    seo_score = int((seo_hits / 4) * 100)
    imgs = soup.find_all('img') if soup else []
    with_alt = [img for img in imgs if img.get('alt')]
    alt_ratio = (len(with_alt) / len(imgs)) if imgs else 1.0
    aria_attrs = soup.find_all(attrs={'role': True}) if soup else []
    acc_score = int(min(100, 60 + alt_ratio*40 + min(len(aria_attrs), 20)))
    https_ok = url.startswith('https://')
    favicon_ok = bool(soup.find('link', rel=re.compile('icon', re.I))) if soup else False
    viewport_ok = bool(soup.find('meta', attrs={'name': 'viewport'})) if soup else False
    bp_hits = sum([https_ok, favicon_ok, viewport_ok])
    bp_score = int((bp_hits / 3) * 100)
    csp_meta = soup.find('meta', attrs={'http-equiv': re.compile('Content-Security-Policy', re.I)}) if soup else None
    sec_score = 70 if https_ok else 40
    if csp_meta:
        sec_score += 20
    sec_score = min(100, sec_score)
    category_scores = {
        'Performance': perf_score,
        'SEO': seo_score,
        'Accessibility': acc_score,
        'Best Practices': bp_score,
        'Security': sec_score,
    }
    metrics = {
        'html_size_kb': round(size_kb, 1),
        'external_assets_count': external_assets,
        'title_present': title_ok,
        'meta_description_present': bool(meta_desc),
        'h1_present': h1_ok,
        'canonical_present': canonical_ok,
        'alt_ratio': round(alt_ratio, 2),
        'aria_roles_count': len(aria_attrs),
        'https': https_ok,
        'favicon_present': favicon_ok,
        'viewport_present': viewport_ok,
    }
    top_issues = []
    if not https_ok:
        top_issues.append('Enable HTTPS for your site')
    if seo_score < 80:
        if not title_ok:
            top_issues.append('Add a descriptive <title> ~ 50–60 chars')
        if not meta_desc:
            top_issues.append('Add a meta description (120–160 chars)')
        if not h1_ok:
            top_issues.append('Include a clear <h1> on the page')
    if perf_score < 80:
        top_issues.append('Reduce HTML size and external assets (bundle/minify)')
    if acc_score < 80:
        top_issues.append('Ensure <img> have meaningful alt text')
    return {
        'category_scores': category_scores,
        'metrics': metrics,
        'top_issues': top_issues,
    }
