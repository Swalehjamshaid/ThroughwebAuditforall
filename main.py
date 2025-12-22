
import io, requests, urllib3, time, random, re, json
from typing import Dict, List, Tuple, Callable, Optional
from urllib.parse import urljoin, urlparse
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
from fpdf import FPDF

# Silence SSL warnings for sites without proper cert chains.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI(title="FF TECH ELITE")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ====================== CATEGORY WEIGHTS (Total 100% Impact) ======================
# Critical categories have higher multipliers in the final grade calculation.
CATEGORY_IMPACT: Dict[str, float] = {
    "Technical SEO": 1.5,   # Critical
    "Security": 1.4,        # Critical
    "Performance": 1.3,     # High
    "On-Page SEO": 1.2,     # High
    "User Experience & Mobile": 1.1,
    "Accessibility": 0.8,
    "Advanced SEO & Analytics": 0.7
}

# Metric list (names & weights). Scoring is handled by evaluators below.
CATEGORIES: Dict[str, List[Tuple[str, int]]] = {
    "Technical SEO": [
        ("HTTPS Enabled", 10), ("Title Tag Present", 10), ("Meta Description Present", 10),
        ("Canonical Tag Present", 8), ("Robots.txt Accessible", 7), ("XML Sitemap Exists", 7),
        ("Structured Data Markup", 6), ("404 Page Properly Configured", 5), ("Redirects Optimized", 5),
        ("URL Structure SEO-Friendly", 5), ("Pagination Tags Correct", 5), ("Hreflang Implementation", 5),
        ("Mobile-Friendly Meta Tag", 5), ("No Broken Links", 4), ("Meta Robots Configured", 4),
        ("Server Response 200 OK", 10), ("Compression Enabled", 4), ("No Duplicate Content", 5),
        ("Crawl Budget Efficient", 3), ("Content Delivery Network Used", 3)
    ],
    "On-Page SEO": [
        ("Single H1 Tag", 10), ("Heading Structure Correct (H2/H3)", 8),
        ("Image ALT Attributes", 7), ("Internal Linking Present", 6), ("Keyword Usage Optimized", 7),
        ("Content Readability", 6), ("Content Freshness", 5), ("Outbound Links Quality", 5),
        ("Schema Markup Correct", 5), ("Canonicalization of Duplicates", 5), ("Breadcrumb Navigation", 4),
        ("No Thin Content", 8), ("Meta Title Length Optimal", 5), ("Meta Description Length Optimal", 5),
        ("Page Content Matches Intent", 6), ("Image File Names SEO-Friendly", 4)
    ],
    "Performance": [
        ("Page Size Optimized", 9), ("Images Optimized", 8), ("Render Blocking JS Removed", 7),
        ("Lazy Loading Implemented", 6), ("Caching Configured", 7), ("Server Response Time < 200ms", 10),
        ("First Contentful Paint < 1.5s", 8), ("Largest Contentful Paint < 2.5s", 10),
        ("Total Blocking Time < 150ms", 8), ("Cumulative Layout Shift < 0.1", 8),
        ("Resource Compression (gzip/brotli)", 7), ("HTTP/2 Enabled", 5), ("Critical CSS Inline", 4),
        ("Font Optimization", 4), ("Third-party Scripts Minimal", 5), ("Async/Defer Scripts Used", 5)
    ],
    "Accessibility": [
        ("Alt Text Coverage", 8), ("Color Contrast Compliant", 7), ("ARIA Roles Correct", 6),
        ("Keyboard Navigation Works", 7), ("Form Labels Correct", 5), ("Semantic HTML Used", 6),
        ("Accessible Media (Captions)", 5), ("Skip Links Present", 4), ("Focus Indicators Visible", 4),
        ("Screen Reader Compatibility", 6), ("No Auto-Playing Media", 4), ("Responsive Text Sizes", 4)
    ],
    "Security": [
        ("No Mixed Content", 10), ("No Exposed Emails", 8), ("HTTPS Enforced", 10),
        ("HSTS Configured", 8), ("Secure Cookies", 7), ("Content Security Policy", 7),
        ("XSS Protection", 6), ("SQL Injection Protection", 7), ("Clickjacking Protection", 5),
        ("Secure Login Forms", 6), ("Password Policies Strong", 5), ("Regular Security Headers", 6)
    ],
    "User Experience & Mobile": [
        ("Mobile Responsiveness", 10), ("Touch Target Sizes Adequate", 8), ("Viewport Configured", 9),
        ("Interactive Elements Accessible", 7), ("Navigation Intuitive", 7), ("Popups/Ads Non-Intrusive", 6),
        ("Fast Interaction Response", 7), ("Sticky Navigation Useful", 4), ("Consistent Branding", 5),
        ("User Journey Optimized", 6), ("Scroll Behavior Smooth", 4), ("Minimal Clutter", 4)
    ],
    "Advanced SEO & Analytics": [
        ("Structured Data Markup", 8), ("Canonical Tags Correct", 8), ("Analytics Tracking Installed", 9),
        ("Conversion Events Tracked", 7), ("Search Console Connected", 7), ("Sitemap Submitted", 6),
        ("Backlink Quality Assessed", 6), ("Core Web Vitals Monitoring", 8), ("Social Meta Tags Present", 5),
        ("Robots Meta Tag Optimization", 5), ("Schema FAQ/Article/Video", 5)
    ]
}

# ====================== Utilities ======================

DEFAULT_TIMEOUT = 12  # seconds
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'FFTechElite/3.0'})
ADDITIONAL_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
}

def ensure_http_scheme(u: str) -> str:
    u = u.strip()
    if not u.startswith("http://") and not u.startswith("https://"):
        u = "https://" + u
    return u

def domain_of(u: str) -> str:
    return urlparse(u).netloc.lower()

def safe_get(url: str, **kwargs) -> Optional[requests.Response]:
    try:
        return SESSION.get(url, timeout=kwargs.get('timeout', DEFAULT_TIMEOUT), verify=False, allow_redirects=True, headers=ADDITIONAL_HEADERS)
    except Exception:
        return None

def safe_head(url: str, **kwargs) -> Optional[requests.Response]:
    try:
        return SESSION.head(url, timeout=kwargs.get('timeout', DEFAULT_TIMEOUT), verify=False, allow_redirects=True, headers=ADDITIONAL_HEADERS)
    except Exception:
        return None

def text_len(s: Optional[str]) -> int:
    return len(s.strip()) if s else 0

def ratio(part: int, whole: int) -> float:
    return (part / whole) if whole > 0 else 0.0

def clamp(v: float, min_v: float = 0.0, max_v: float = 100.0) -> float:
    return max(min_v, min(max_v, v))

def map_linear(value: float, min_val: float, max_val: float) -> float:
    """Map a value to 0..100 linearly where min_val->100 (good), max_val->0 (bad)."""
    if value <= min_val:
        return 100.0
    if value >= max_val:
        return 0.0
    # rotate so smaller is better
    return 100.0 * (max_val - value) / (max_val - min_val)

def has_csp(headers: Dict[str, str]) -> bool:
    return any(h.lower() == 'content-security-policy' for h in headers.keys())

def has_hsts(headers: Dict[str, str]) -> bool:
    return any(h.lower() == 'strict-transport-security' for h in headers.keys())

def security_headers_present(headers: Dict[str, str]) -> int:
    expected = [
        'strict-transport-security',
        'content-security-policy',
        'x-content-type-options',
        'x-frame-options',
        'referrer-policy',
        'permissions-policy',
    ]
    present = sum(1 for k in headers.keys() if k.lower() in expected)
    return present

def cookies_flags_secure(resp: requests.Response) -> float:
    # Simple scan of Set-Cookie for Secure/HttpOnly/SameSite
    set_cookies = resp.headers.get('Set-Cookie', '')
    if not set_cookies:
        return 50.0  # neutral if no cookies found
    flags_good = 0
    cookies = set_cookies.split('\n')
    for c in cookies:
        c_low = c.lower()
        good = ('secure' in c_low) + ('httponly' in c_low) + ('samesite' in c_low)
        flags_good += good
    # map to 0..100, 3 flags per cookie as maximum
    return clamp(100.0 * flags_good / (len(cookies) * 3))

def check_mixed_content(soup: BeautifulSoup, base_url: str) -> float:
    # If page is https, count http resources
    if not base_url.startswith('https://'):
        return 50.0  # neutral (not applicable)
    http_refs = 0
    total_refs = 0
    for tag, attr in [('img','src'), ('script','src'), ('link','href'), ('iframe','src')]:
        for el in soup.find_all(tag):
            ref = el.get(attr)
            if not ref:
                continue
            total_refs += 1
            abs_ref = urljoin(base_url, ref)
            if abs_ref.startswith('http://'):
                http_refs += 1
    if total_refs == 0:
        return 100.0
    return clamp(100.0 * (1.0 - ratio(http_refs, total_refs)))

def sample_internal_links_status(soup: BeautifulSoup, base_url: str, max_links: int = 10) -> float:
    base_domain = domain_of(base_url)
    links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('#'):
            continue
        abs_href = urljoin(base_url, href)
        d = domain_of(abs_href)
        if d == base_domain or href.startswith('/'):
            links.append(abs_href)
    sampled = list(dict.fromkeys(links))[:max_links]
    if not sampled:
        return 50.0  # neutral if no internal links
    ok = 0
    for lnk in sampled:
        resp = safe_head(lnk, timeout=6) or safe_get(lnk, timeout=6)
        if resp and (200 <= resp.status_code < 400):
            ok += 1
    return clamp(100.0 * ratio(ok, len(sampled)))

def is_http_redirect_to_https(url: str) -> bool:
    if url.startswith('https://'):
        return True
    http_url = 'http://' + urlparse(url).netloc + urlparse(url).path
    resp = safe_get(http_url, timeout=8)
    if not resp:
        return False
    final = resp.url
    return final.startswith('https://')

def count_blocking_scripts(soup: BeautifulSoup) -> int:
    head = soup.find('head')
    if not head:
        return 0
    cnt = 0
    for s in head.find_all('script'):
        # blocking if no async/defer and has src or content
        if not s.has_attr('async') and not s.has_attr('defer'):
            if s.get('src') or (s.string and text_len(s.string) > 0):
                cnt += 1
    return cnt

def lazy_img_ratio(soup: BeautifulSoup) -> float:
    imgs = soup.find_all('img')
    if not imgs:
        return 50.0
    lazy = sum(1 for i in imgs if i.get('loading', '').lower() == 'lazy')
    return clamp(100.0 * ratio(lazy, len(imgs)))

def images_have_dimensions_ratio(soup: BeautifulSoup) -> float:
    imgs = soup.find_all('img')
    if not imgs:
        return 50.0
    with_dims = 0
    for i in imgs:
        if i.get('width') or i.get('height'):
            with_dims += 1
    return clamp(100.0 * ratio(with_dims, len(imgs)))

def page_size_score(resp: requests.Response) -> float:
    size_bytes = len(resp.content or b'')
    # 0..100 where <= 1MB is 100, >= 3MB is 0
    return map_linear(size_bytes, 1_000_000, 3_000_000)

def caching_score(headers: Dict[str, str]) -> float:
    cc = headers.get('Cache-Control', '') or headers.get('cache-control', '')
    if not cc:
        return 40.0
    # score higher if max-age >= 600
    max_age_match = re.search(r'max-age=(\d+)', cc, flags=re.IGNORECASE)
    if max_age_match:
        try:
            age = int(max_age_match.group(1))
            return clamp(map_linear(600 - age, -3600, 0))  # age >=600 => ~100
        except ValueError:
            pass
    # at least caching header exists
    return 70.0

def compression_score(headers: Dict[str, str]) -> float:
    enc = headers.get('Content-Encoding', '') or headers.get('content-encoding', '')
    if enc:
        if 'br' in enc.lower() or 'gzip' in enc.lower():
            return 100.0
        return 60.0
    return 30.0

def http2_guess(headers: Dict[str, str]) -> float:
    # Requests does not expose ALPN protocol. Provide neutral score if unknown.
    # If via Cloudflare/Akamai/Fastly, assume likely HTTP/2.
    server = (headers.get('Server') or headers.get('server') or '').lower()
    via = (headers.get('Via') or headers.get('via') or '').lower()
    cdns = ['cloudflare', 'akamai', 'fastly', 'google', 'gws']
    if any(cdn in server or cdn in via for cdn in cdns):
        return 85.0
    return 60.0

def readability_score(text: str) -> float:
    # Simple heuristic: shorter sentences/words => better readability
    words = re.findall(r'\w+', text)
    sentences = re.split(r'[.!?]+', text)
    w_count = len(words)
    s_count = len([s for s in sentences if text_len(s) > 0]) or 1
    avg_w_per_s = w_count / s_count
    # 0..100 map, where <= 20 words per sentence is good, >= 35 is bad
    return clamp(map_linear(avg_w_per_s, 20, 35))

def freshness_score(resp: requests.Response, soup: BeautifulSoup) -> float:
    # Check Last-Modified header or article published meta
    lm = resp.headers.get('Last-Modified', '') or resp.headers.get('last-modified', '')
    if lm:
        return 90.0  # header present is good
    meta_pub = soup.find('meta', {'property': 'article:published_time'}) or soup.find('meta', {'name': 'date'})
    if meta_pub and meta_pub.get('content'):
        return 80.0
    return 50.0

def analytics_installed(soup: BeautifulSoup) -> float:
    html = str(soup)
    tags = [
        'www.googletagmanager.com/gtag/js',
        'google-analytics.com/analytics.js',
        'gtm.js',
        'dataLayer.push',
        'clarity.ms',
        'umami.is',
        'mixpanel.com',
        'static.hotjar.com',
        'facebook.net/en_US/fbevents.js',
    ]
    found = sum(1 for t in tags if t in html)
    return clamp(min(100.0, 40.0 + found * 15.0))

def social_meta_present(soup: BeautifulSoup) -> float:
    og = soup.find('meta', {'property':'og:title'}) or soup.find('meta', {'property':'og:image'})
    tw = soup.find('meta', {'name':'twitter:card'}) or soup.find('meta', {'name':'twitter:title'})
    return 100.0 if (og or tw) else 50.0

def robots_meta_optimization(soup: BeautifulSoup) -> float:
    m = soup.find('meta', {'name':'robots'})
    if not m:
        return 60.0
    content = (m.get('content','') or '').lower()
    good = ('index' in content and 'follow' in content)
    return 100.0 if good else 70.0

def schema_present(soup: BeautifulSoup) -> float:
    # JSON-LD or microdata
    ld = soup.find_all('script', {'type':'application/ld+json'})
    microdata_items = soup.find_all(attrs={'itemtype': True})
    return clamp(min(100.0, 60.0 + (len(ld) + len(microdata_items)) * 10.0))

def breadcrumb_present(soup: BeautifulSoup) -> float:
    # nav[aria-label=breadcrumb] or schema BreadcrumbList
    nav_b = soup.select('nav[aria-label="breadcrumb"]')
    schema_b = soup.find(attrs={'itemtype': re.compile('BreadcrumbList', re.I)})
    return 100.0 if (nav_b or schema_b) else 60.0

def canonical_present(soup: BeautifulSoup) -> float:
    link = soup.find('link', {'rel':'canonical'})
    return 100.0 if link and link.get('href') else 50.0

def pagination_tags(soup: BeautifulSoup) -> float:
    prev = soup.find('link', {'rel':'prev'})
    nxt = soup.find('link', {'rel':'next'})
    return 100.0 if (prev or nxt) else 60.0

def hreflang_impl(soup: BeautifulSoup) -> float:
    alts = soup.find_all('link', {'rel':'alternate'})
    hreflang = [a for a in alts if a.get('hreflang')]
    return clamp(min(100.0, 50.0 + len(hreflang) * 10.0)) if hreflang else 50.0

def meta_title_length_optimal(soup: BeautifulSoup) -> float:
    title = soup.title.string.strip() if soup.title and soup.title.string else ''
    l = len(title)
    # Optimal ~50–60 chars
    if 50 <= l <= 60:
        return 100.0
    if 35 <= l <= 70:
        return 85.0
    return 60.0 if l > 0 else 0.0

def meta_desc_length_optimal(soup: BeautifulSoup) -> float:
    m = soup.find('meta', {'name':'description'})
    content = (m.get('content','') if m else '').strip()
    l = len(content)
    # Optimal ~150–160 chars
    if 150 <= l <= 165:
        return 100.0
    if 100 <= l <= 200:
        return 85.0
    return 60.0 if l > 0 else 0.0

def url_structure_seo_friendly(url: str) -> float:
    p = urlparse(url)
    path = p.path
    # penalize uppercase, long segments, query hash heavy
    bad = 0
    if re.search(r'[A-Z]', path):
        bad += 1
    if len(path) > 80:
        bad += 1
    if '_' in path:
        bad += 1
    if len(p.query) > 0:
        bad += 1
    return clamp(100.0 - bad * 20.0)

def cdn_used(soup: BeautifulSoup, base_url: str) -> float:
    hosts = []
    for tag, attr in [('img','src'), ('script','src'), ('link','href')]:
        for el in soup.find_all(tag):
            ref = el.get(attr)
            if not ref:
                continue
            abs_ref = urljoin(base_url, ref)
            hosts.append(urlparse(abs_ref).netloc.lower())
    cdn_keywords = ['cdn', 'cloudfront', 'cloudflare', 'akamai', 'fastly', 'edgekey']
    used = any(any(k in h for k in cdn_keywords) for h in hosts)
    return 90.0 if used else 60.0

def alt_text_coverage(soup: BeautifulSoup) -> float:
    imgs = soup.find_all('img')
    if not imgs:
        return 70.0
    covered = sum(1 for i in imgs if i.get('alt') and text_len(i.get('alt')) > 0)
    return clamp(100.0 * ratio(covered, len(imgs)))

def internal_linking_present(soup: BeautifulSoup, base_url: str) -> float:
    base_domain = domain_of(base_url)
    count = 0
    for a in soup.find_all('a', href=True):
        href = a['href']
        abs_href = urljoin(base_url, href)
        if domain_of(abs_href) == base_domain or href.startswith('/'):
            count += 1
    if count == 0:
        return 30.0
    return clamp(min(100.0, 50.0 + count))

def color_contrast_compliant() -> float:
    # Not measurable server-side. Neutral score.
    return 60.0

def aria_roles_correct(soup: BeautifulSoup) -> float:
    roles = soup.find_all(attrs={'role': True})
    if not roles:
        return 60.0
    return clamp(min(100.0, 60.0 + len(roles) * 4.0))

def keyboard_nav_works() -> float:
    return 60.0  # server-side unknown

def form_labels_correct(soup: BeautifulSoup) -> float:
    inputs = soup.find_all('input')
    labels = soup.find_all('label')
    if not inputs:
        return 70.0
    # heuristic: at least 40% inputs have labels or aria-label
    labeled = 0
    for inp in inputs:
        id_ = inp.get('id')
        has_label = False
        if id_:
            has_label = any(l.get('for') == id_ for l in labels)
        aria = bool(inp.get('aria-label'))
        if has_label or aria:
            labeled += 1
    return clamp(100.0 * ratio(labeled, len(inputs)))

def semantic_html_used(soup: BeautifulSoup) -> float:
    tags = ['header','nav','main','section','article','aside','footer']
    present = sum(1 for t in tags if soup.find(t))
    return clamp(min(100.0, 50.0 + present * 10.0))

def accessible_media_captions(soup: BeautifulSoup) -> float:
    tracks = soup.find_all('track', {'kind':'captions'})
    return 100.0 if tracks else 60.0

def skip_links_present(soup: BeautifulSoup) -> float:
    a_tags = soup.find_all('a', href=True)
    skips = [a for a in a_tags if a['href'].startswith('#') and 'skip' in (a.text or '').lower()]
    return 100.0 if skips else 60.0

def focus_indicators_visible() -> float:
    return 60.0  # server-side unknown

def screen_reader_compatibility(soup: BeautifulSoup) -> float:
    html_tag = soup.find('html')
    has_lang = html_tag and html_tag.get('lang')
    return 90.0 if has_lang else 70.0

def no_autoplay_media(soup: BeautifulSoup) -> float:
    vids = soup.find_all('video')
    bad = sum(1 for v in vids if v.get('autoplay'))
    return clamp(100.0 - bad * 25.0)

def responsive_text_sizes() -> float:
    return 70.0  # server-side unknown

def mobile_responsiveness(soup: BeautifulSoup) -> float:
    vp = soup.find('meta', {'name':'viewport'})
    css_grid = 'display:grid' in str(soup).lower() or 'grid-template' in str(soup).lower()
    flex = 'display:flex' in str(soup).lower()
    return clamp(50.0 + (20.0 if vp else 0.0) + (15.0 if css_grid else 0.0) + (15.0 if flex else 0.0))

def touch_targets_sizes_adequate() -> float:
    return 60.0  # server-side unknown

def viewport_configured(soup: BeautifulSoup) -> float:
    return 100.0 if soup.find('meta', {'name':'viewport'}) else 60.0

def interactive_elements_accessible(soup: BeautifulSoup) -> float:
    buttons = soup.find_all('button')
    role_buttons = soup.find_all(attrs={'role':'button'})
    return clamp(min(100.0, 60.0 + (len(buttons) + len(role_buttons)) * 5.0))

def navigation_intuitive() -> float:
    return 65.0  # heuristic unknown

def popups_non_intrusive(soup: BeautifulSoup) -> float:
    # crude: modal keywords
    txt = str(soup).lower()
    intrusive = ('modal' in txt and 'popup' in txt)
    return 80.0 if not intrusive else 60.0

def fast_interaction_response(blocking_scripts: int) -> float:
    # less blocking scripts -> faster interaction
    return clamp(map_linear(blocking_scripts, 0, 6))

def sticky_navigation_useful(soup: BeautifulSoup) -> float:
    # look for CSS position:sticky hints
    return 70.0 if 'position:sticky' in str(soup).lower() else 60.0

def consistent_branding() -> float:
    return 70.0  # unknown server-side

def user_journey_optimized() -> float:
    return 65.0  # unknown

def smooth_scroll_behavior(soup: BeautifulSoup) -> float:
    return 80.0 if 'scroll-behavior:smooth' in str(soup).replace(" ", "").lower() else 60.0

def minimal_clutter(soup: BeautifulSoup) -> float:
    # heuristic: number of scripts/styles too many -> clutter
    scripts = len(soup.find_all('script'))
    styles = len(soup.find_all('link', {'rel':'stylesheet'}))
    return clamp(map_linear(scripts + styles, 10, 40))

def meta_robots_configured(soup: BeautifulSoup) -> float:
    return 100.0 if soup.find('meta', {'name':'robots'}) else 70.0

def server_response_200_ok(resp: requests.Response) -> float:
    return 100.0 if resp.status_code == 200 else 0.0

def first_contentful_paint_proxy(blocking_scripts: int, page_size_bytes: int) -> float:
    # proxy: lower blocking scripts + smaller page -> better FCP
    base = clamp(map_linear(blocking_scripts, 0, 8))
    size_penalty = clamp(map_linear(page_size_bytes, 800_000, 2_500_000))
    return clamp((base * 0.6) + (size_penalty * 0.4))

def largest_contentful_paint_proxy(images_dims_ratio: float, page_size_bytes: int) -> float:
    base = images_dims_ratio
    size_penalty = clamp(map_linear(page_size_bytes, 1_200_000, 3_000_000))
    return clamp((base * 0.6) + (size_penalty * 0.4))

def total_blocking_time_proxy(blocking_scripts: int) -> float:
    return clamp(map_linear(blocking_scripts * 80, 100, 800))  # assume ~80ms per blocking script

def cumulative_layout_shift_proxy(images_dims_ratio: float) -> float:
    # more images with dimensions -> less CLS
    return clamp(images_dims_ratio)

def async_defer_scripts_used(soup: BeautifulSoup) -> float:
    scripts = soup.find_all('script')
    if not scripts:
        return 70.0
    asyncdefer = sum(1 for s in scripts if s.has_attr('async') or s.has_attr('defer'))
    return clamp(100.0 * ratio(asyncdefer, len(scripts)))

def third_party_scripts_minimal(soup: BeautifulSoup, base_url: str) -> float:
    base_domain = domain_of(base_url)
    scripts = soup.find_all('script', src=True)
    if not scripts:
        return 90.0
    third = 0
    for s in scripts:
        d = domain_of(urljoin(base_url, s['src']))
        if d and d != base_domain:
            third += 1
    return clamp(map_linear(third, 2, 12))

def critical_css_inline(soup: BeautifulSoup) -> float:
    style_tags = soup.find_all('style')
    head = soup.find('head')
    if not head:
        return 60.0
    inline_in_head = sum(1 for s in style_tags if s in head.descendants)
    return clamp(min(100.0, 60.0 + inline_in_head * 10.0))

def font_optimization(soup: BeautifulSoup) -> float:
    # check font-display swap
    styles = soup.find_all('style')
    css_text = ' '.join([s.get_text() or '' for s in styles])
    # also look for Google Fonts with display=swap
    links = soup.find_all('link', href=True)
    swap = 'font-display: swap' in css_text.lower() or any('display=swap' in l['href'].lower() for l in links)
    return 90.0 if swap else 60.0

def no_duplicate_content() -> float:
    # Requires crawl; provide neutral
    return 60.0

def crawl_budget_efficient(soup: BeautifulSoup) -> float:
    # heuristic: number of links capped
    a_count = len(soup.find_all('a'))
    return clamp(map_linear(a_count, 100, 600))

def redirects_optimized(resp: requests.Response) -> float:
    hops = len(resp.history or [])
    return clamp(map_linear(hops, 0, 4))

def structured_data_markup(soup: BeautifulSoup) -> float:
    return schema_present(soup)

def xml_sitemap_exists(base_url: str, robots_txt: Optional[str]) -> float:
    # Check /sitemap.xml or robots.txt 'Sitemap:' lines
    sitemap_url = urljoin(base_url, '/sitemap.xml')
    resp = safe_head(sitemap_url, timeout=6) or safe_get(sitemap_url, timeout=6)
    if resp and resp.status_code < 400:
        return 100.0
    if robots_txt and 'sitemap:' in robots_txt.lower():
        return 80.0
    return 60.0

def robots_txt_accessible(base_url: str) -> Tuple[float, Optional[str]]:
    rt_url = urljoin(base_url, '/robots.txt')
    resp = safe_get(rt_url, timeout=6)
    if resp and resp.status_code < 400:
        return 100.0, resp.text
    return 60.0, None

def meta_description_present(soup: BeautifulSoup) -> float:
    return 100.0 if soup.find('meta', {'name':'description'}) else 0.0

def single_h1_tag(soup: BeautifulSoup) -> float:
    h1s = soup.find_all('h1')
    return 100.0 if len(h1s) == 1 else (80.0 if len(h1s) > 1 else 0.0)

def heading_structure_correct(soup: BeautifulSoup) -> float:
    h2 = len(soup.find_all('h2'))
    h3 = len(soup.find_all('h3'))
    if h2 > 0 and h3 > 0:
        return 100.0
    if h2 + h3 > 0:
        return 80.0
    return 60.0

def image_alt_attributes(soup: BeautifulSoup) -> float:
    return alt_text_coverage(soup)

def image_file_names_seo_friendly(soup: BeautifulSoup) -> float:
    imgs = soup.find_all('img', src=True)
    if not imgs:
        return 70.0
    good = 0
    for i in imgs:
        name = urlparse(urljoin('http://dummy', i['src'])).path.split('/')[-1]
        # heuristic: contains letters, not just numbers/hash
        if re.search(r'[a-zA-Z]', name) and not re.search(r'^[0-9a-f]{16,}$', name):
            good += 1
    return clamp(100.0 * ratio(good, len(imgs)))

def outbound_links_quality(soup: BeautifulSoup, base_url: str) -> float:
    base_domain = domain_of(base_url)
    a_tags = soup.find_all('a', href=True)
    out = [a for a in a_tags if (domain_of(urljoin(base_url, a['href'])) != base_domain)]
    if not out:
        return 60.0
    # reward rel=nofollow/sponsored presence
    good = 0
    for a in out:
        rel = (a.get('rel') or [])
        rel_low = ' '.join(rel).lower()
        if 'nofollow' in rel_low or 'sponsored' in rel_low:
            good += 1
    return clamp(60.0 + 40.0 * ratio(good, len(out)))

def conversion_events_tracked(soup: BeautifulSoup) -> float:
    txt = str(soup)
    cues = ['purchase', 'add_to_cart', 'begin_checkout', 'lead', 'generate_lead', 'sign_up', 'login']
    found = sum(1 for c in cues if c in txt.lower())
    return clamp(min(100.0, 60.0 + found * 10.0))

def google_search_console_connected(soup: BeautifulSoup) -> float:
    meta_ver = soup.find('meta', {'name':'google-site-verification'})
    return 100.0 if meta_ver else 60.0

def sitemap_submitted(robots_txt: Optional[str]) -> float:
    return 90.0 if robots_txt and 'sitemap:' in robots_txt.lower() else 60.0

def backlink_quality_assessed() -> float:
    return 50.0  # server-side unknown without offsite data

def core_web_vitals_monitoring(soup: BeautifulSoup) -> float:
    txt = str(soup).lower()
    # looking for web-vitals or custom measurement
    return 85.0 if 'web-vitals' in txt or 'largestcontentfulpaint' in txt or 'firstcontentfulpaint' in txt else 60.0

def schema_faq_article_video(soup: BeautifulSoup) -> float:
    ld_jsons = soup.find_all('script', {'type':'application/ld+json'})
    txts = [j.get_text() or '' for j in ld_jsons]
    hit = any(any(k in t.lower() for k in ['faqpage','article','videobject','howto']) for t in txts)
    return 90.0 if hit else 60.0

def no_exposed_emails(soup: BeautifulSoup) -> float:
    # simple regex; false positives possible
    emails = re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', str(soup))
    return clamp(map_linear(len(emails), 0, 5))

def xss_protection(headers: Dict[str, str]) -> float:
    # Modern CSP supersedes X-XSS-Protection
    if has_csp(headers):
        return 90.0
    x_xss = headers.get('X-XSS-Protection') or headers.get('x-xss-protection')
    return 70.0 if x_xss else 60.0

def sql_injection_protection(headers: Dict[str, str]) -> float:
    # Heuristic: presence of WAF/CDN headers
    waf_headers = ['x-waf', 'cf-ray', 'x-akamai', 'server']
    val = any(h in (k.lower()) for k in headers.keys() for h in waf_headers)
    return 75.0 if val else 60.0

def clickjacking_protection(headers: Dict[str, str]) -> float:
    xfo = headers.get('X-Frame-Options') or headers.get('x-frame-options')
    csp = headers.get('Content-Security-Policy') or headers.get('content-security-policy')
    if xfo:
        return 95.0
    if csp and 'frame-ancestors' in csp.lower():
        return 95.0
    return 60.0

def secure_login_forms(soup: BeautifulSoup, base_url: str) -> float:
    forms = soup.find_all('form')
    login_like = [f for f in forms if re.search(r'password|login', str(f).lower())]
    if not login_like:
        return 70.0
    # reward if site is HTTPS and inputs type=password present
    https = base_url.startswith('https://')
    pwd_inputs = sum(1 for f in login_like for i in f.find_all('input') if i.get('type','').lower() == 'password')
    return clamp(70.0 + (20.0 if https else 0.0) + (10.0 if pwd_inputs > 0 else 0.0))

def password_policies_strong() -> float:
    return 60.0  # cannot verify

def regular_security_headers(headers: Dict[str, str]) -> float:
    present = security_headers_present(headers)
    return clamp(min(100.0, 50.0 + present * 8.0))

# ====================== Evaluator Map ======================

def build_evaluators(base_url: str, resp: requests.Response, soup: BeautifulSoup, robots_txt: Optional[str], ttfb_ms: float) -> Dict[str, Callable[[], float]]:
    blocking_scripts = count_blocking_scripts(soup)
    page_bytes = len(resp.content or b'')
    images_dims_ratio_val = images_have_dimensions_ratio(soup)

    headers = resp.headers

    return {
        # Technical SEO
        "HTTPS Enabled": lambda: (100.0 if base_url.startswith('https://') else 0.0),
        "Title Tag Present": lambda: (100.0 if soup.title and text_len(soup.title.string or '') > 0 else 0.0),
        "Meta Description Present": lambda: meta_description_present(soup),
        "Canonical Tag Present": lambda: canonical_present(soup),
        "Robots.txt Accessible": lambda: (100.0 if robots_txt is not None else 60.0),
        "XML Sitemap Exists": lambda: xml_sitemap_exists(base_url, robots_txt),
        "Structured Data Markup": lambda: structured_data_markup(soup),
        "404 Page Properly Configured": lambda: (100.0 if (safe_get(urljoin(base_url, '/__fftech_elite_404_test__'), timeout=6) or type('x', (), {'status_code': 404})) and ((safe_get(urljoin(base_url, '/__fftech_elite_404_test__'), timeout=6) or None) and (safe_get(urljoin(base_url, '/__fftech_elite_404_test__'), timeout=6).status_code == 404)) else 70.0),
        "Redirects Optimized": lambda: redirects_optimized(resp),
        "URL Structure SEO-Friendly": lambda: url_structure_seo_friendly(base_url),
        "Pagination Tags Correct": lambda: pagination_tags(soup),
        "Hreflang Implementation": lambda: hreflang_impl(soup),
        "Mobile-Friendly Meta Tag": lambda: viewport_configured(soup),
        "No Broken Links": lambda: sample_internal_links_status(soup, base_url),
        "Meta Robots Configured": lambda: meta_robots_configured(soup),
        "Server Response 200 OK": lambda: server_response_200_ok(resp),
        "Compression Enabled": lambda: compression_score(headers),
        "No Duplicate Content": lambda: no_duplicate_content(),
        "Crawl Budget Efficient": lambda: crawl_budget_efficient(soup),
        "Content Delivery Network Used": lambda: cdn_used(soup, base_url),

        # On-Page SEO
        "Single H1 Tag": lambda: single_h1_tag(soup),
        "Heading Structure Correct (H2/H3)": lambda: heading_structure_correct(soup),
        "Image ALT Attributes": lambda: image_alt_attributes(soup),
        "Internal Linking Present": lambda: internal_linking_present(soup, base_url),
        "Keyword Usage Optimized": lambda: 60.0,  # server-side unknown
        "Content Readability": lambda: readability_score(soup.get_text(separator=' ')),
        "Content Freshness": lambda: freshness_score(resp, soup),
        "Outbound Links Quality": lambda: outbound_links_quality(soup, base_url),
        "Schema Markup Correct": lambda: schema_present(soup),
        "Canonicalization of Duplicates": lambda: canonical_present(soup),
        "Breadcrumb Navigation": lambda: breadcrumb_present(soup),
        "No Thin Content": lambda: clamp(map_linear(text_len(soup.get_text()), 1_500, 300)),  # more text is better
        "Meta Title Length Optimal": lambda: meta_title_length_optimal(soup),
        "Meta Description Length Optimal": lambda: meta_desc_length_optimal(soup),
        "Page Content Matches Intent": lambda: 65.0,  # unknown
        "Image File Names SEO-Friendly": lambda: image_file_names_seo_friendly(soup),

        # Performance
        "Page Size Optimized": lambda: page_size_score(resp),
        "Images Optimized": lambda: clamp((lazy_img_ratio(soup) * 0.5) + (images_dims_ratio_val * 0.5)),
        "Render Blocking JS Removed": lambda: clamp(map_linear(count_blocking_scripts(soup), 0, 6)),
        "Lazy Loading Implemented": lambda: lazy_img_ratio(soup),
        "Caching Configured": lambda: caching_score(headers),
        "Server Response Time < 200ms": lambda: clamp(map_linear(ttfb_ms, 200, 1200)),
        "First Contentful Paint < 1.5s": lambda: first_contentful_paint_proxy(blocking_scripts, page_bytes),
        "Largest Contentful Paint < 2.5s": lambda: largest_contentful_paint_proxy(images_dims_ratio_val, page_bytes),
        "Total Blocking Time < 150ms": lambda: total_blocking_time_proxy(blocking_scripts),
        "Cumulative Layout Shift < 0.1": lambda: cumulative_layout_shift_proxy(images_dims_ratio_val),
        "Resource Compression (gzip/brotli)": lambda: compression_score(headers),
        "HTTP/2 Enabled": lambda: http2_guess(headers),
        "Critical CSS Inline": lambda: critical_css_inline(soup),
        "Font Optimization": lambda: font_optimization(soup),
        "Third-party Scripts Minimal": lambda: third_party_scripts_minimal(soup, base_url),
        "Async/Defer Scripts Used": lambda: async_defer_scripts_used(soup),

        # Accessibility
        "Alt Text Coverage": lambda: alt_text_coverage(soup),
        "Color Contrast Compliant": lambda: color_contrast_compliant(),
        "ARIA Roles Correct": lambda: aria_roles_correct(soup),
        "Keyboard Navigation Works": lambda: keyboard_nav_works(),
        "Form Labels Correct": lambda: form_labels_correct(soup),
        "Semantic HTML Used": lambda: semantic_html_used(soup),
        "Accessible Media (Captions)": lambda: accessible_media_captions(soup),
        "Skip Links Present": lambda: skip_links_present(soup),
        "Focus Indicators Visible": lambda: focus_indicators_visible(),
        "Screen Reader Compatibility": lambda: screen_reader_compatibility(soup),
        "No Auto-Playing Media": lambda: no_autoplay_media(soup),
        "Responsive Text Sizes": lambda: responsive_text_sizes(),

        # Security
        "No Mixed Content": lambda: check_mixed_content(soup, base_url),
        "No Exposed Emails": lambda: no_exposed_emails(soup),
        "HTTPS Enforced": lambda: (100.0 if is_http_redirect_to_https(base_url) else (90.0 if base_url.startswith('https://') else 50.0)),
        "HSTS Configured": lambda: (100.0 if has_hsts(headers) else 60.0),
        "Secure Cookies": lambda: cookies_flags_secure(resp),
        "Content Security Policy": lambda: (95.0 if has_csp(headers) else 60.0),
        "XSS Protection": lambda: xss_protection(headers),
        "SQL Injection Protection": lambda: sql_injection_protection(headers),
        "Clickjacking Protection": lambda: clickjacking_protection(headers),
        "Secure Login Forms": lambda: secure_login_forms(soup, base_url),
        "Password Policies Strong": lambda: password_policies_strong(),
        "Regular Security Headers": lambda: regular_security_headers(headers),

        # UX/Mobile
        "Mobile Responsiveness": lambda: mobile_responsiveness(soup),
        "Touch Target Sizes Adequate": lambda: touch_targets_sizes_adequate(),
        "Viewport Configured": lambda: viewport_configured(soup),
        "Interactive Elements Accessible": lambda: interactive_elements_accessible(soup),
        "Navigation Intuitive": lambda: navigation_intuitive(),
        "Popups/Ads Non-Intrusive": lambda: popups_non_intrusive(soup),
        "Fast Interaction Response": lambda: fast_interaction_response(blocking_scripts),
        "Sticky Navigation Useful": lambda: sticky_navigation_useful(soup),
        "Consistent Branding": lambda: consistent_branding(),
        "User Journey Optimized": lambda: user_journey_optimized(),
        "Scroll Behavior Smooth": lambda: smooth_scroll_behavior(soup),
        "Minimal Clutter": lambda: minimal_clutter(soup),

        # Advanced SEO & Analytics
        "Canonical Tags Correct": lambda: canonical_present(soup),
        "Analytics Tracking Installed": lambda: analytics_installed(soup),
        "Conversion Events Tracked": lambda: conversion_events_tracked(soup),
        "Search Console Connected": lambda: google_search_console_connected(soup),
        "Sitemap Submitted": lambda: sitemap_submitted(robots_txt),
        "Backlink Quality Assessed": lambda: backlink_quality_assessed(),
        "Core Web Vitals Monitoring": lambda: core_web_vitals_monitoring(soup),
        "Social Meta Tags Present": lambda: social_meta_present(soup),
        "Robots Meta Tag Optimization": lambda: robots_meta_optimization(soup),
        "Schema FAQ/Article/Video": lambda: schema_faq_article_video(soup),
    }

# ====================== API: /audit ======================

@app.post("/audit")
async def audit(req: Request):
    data = await req.json()
    url = ensure_http_scheme(data.get("url", "").strip())
    if not url or domain_of(url) == "":
        raise HTTPException(status_code=400, detail="Invalid URL")

    # Fetch main page and measure TTFB
    try:
        start_time = time.time()
        r = safe_get(url, timeout=DEFAULT_TIMEOUT)
        if r is None:
            raise HTTPException(status_code=400, detail="Site Unreachable")
        ttfb = (time.time() - start_time) * 1000.0
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception:
        raise HTTPException(status_code=400, detail="Site Unreachable")

    # Robots.txt (used in multiple evaluators)
    robots_score, robots_txt = robots_txt_accessible(url)

    metrics: List[Dict[str, object]] = []
    total_weighted_points = 0.0
    total_possible_weight = 0.0

    evaluators = build_evaluators(url, r, soup, robots_txt, ttfb)

    # ===== Deterministic Scoring Logic =====
    for category, checks in CATEGORIES.items():
        cat_impact = CATEGORY_IMPACT.get(category, 1.0)
        for name, weight in checks:
            # compute score with evaluator if present else neutral 60
            try:
                evaluator = evaluators.get(name, lambda: 60.0)
                score_val = clamp(float(evaluator()))
            except Exception:
                score_val = 50.0  # safe fallback if evaluator errors

            metrics.append({"name": name, "score": round(score_val), "category": category})
            total_weighted_points += (score_val * weight * cat_impact)
            total_possible_weight += (100.0 * weight * cat_impact)

    total_grade = round((total_weighted_points / total_possible_weight) * 100)

    summary = (
        f"The FF TECH ELITE Forensic Audit of {url} has concluded with an overall Health Score of {total_grade}%. "
        "This engine uses a Weighted Impact Model where Technical SEO and Security carry the highest influence on the final grade.\n\n"
        f"Strategic Findings: The site shows a measured Time To First Byte (TTFB) of {round(ttfb)}ms. "
        f"This is {'optimal' if ttfb < 200 else 'moderate' if ttfb < 800 else 'sub-optimal'} and directly affects the Performance score. "
        "We evaluated canonicalization, robots & sitemap availability, structured data, accessibility heuristics, and multiple security headers "
        "(HSTS, CSP, clickjacking, cookies flags). Performance proxies consider page size, resource compression, caching signals, and render-blocking scripts.\n\n"
        "Recommendations: Prioritize 'Technical SEO' (canonical, robots/sitemap, hreflang) and 'Security' (HSTS, CSP, secure cookies). "
        "Then address Performance (caching, compression, blocking JS, lazy loading) and On-Page structure (titles, descriptions, headings, alt coverage). "
        "Finally, ensure analytics/conversion tracking and social preview tags are consistently implemented to support 2025 growth."
    )

    return {"total_grade": total_grade, "summary": summary, "metrics": metrics}

# ====================== PDF Export ======================

class ElitePDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, "FF TECH | ELITE STRATEGIC INTELLIGENCE 2025", ln=1, align="C")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 9)
        self.cell(0, 10, f"Generated by FFTech Elite • Page {self.page_no()}", align="C")

def build_pdf(report: Dict[str, object]) -> bytes:
    pdf = ElitePDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Title + Grade
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "Forensic Audit Report", ln=1)
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 8, f"Overall Health Score: {report.get('total_grade', 0)}%", ln=1)
    pdf.ln(4)

    # Summary
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Strategic Overview", ln=1)
    pdf.set_font("Helvetica", "", 11)
    # Multi-cell for wrapped text
    summary_text = str(report.get("summary", ""))
    pdf.multi_cell(0, 6, summary_text)
    pdf.ln(4)

    # Metrics grouped by category
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Detailed Metrics", ln=1)
    pdf.set_font("Helvetica", "", 10)

    metrics: List[Dict[str, object]] = report.get("metrics", [])
    # Group by category
    grouped: Dict[str, List[Dict[str, object]]] = {}
    for m in metrics:
        grouped.setdefault(m["category"], []).append(m)

    for cat, items in grouped.items():
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, f"{cat}", ln=1)
        pdf.set_font("Helvetica", "", 10)
        # two-column layout
        col_width = pdf.w - 30
        half = col_width / 2.0
        for i, item in enumerate(items):
            name = str(item["name"])
            score = int(item["score"])
            line = f"• {name} — {score}%"
            if i % 2 == 0:
                pdf.cell(half, 6, line, ln=0)
            else:
                pdf.cell(half, 6, line, ln=1)
        if len(items) % 2 == 1:
            pdf.ln(6)
        else:
            pdf.ln(3)

    # Final note
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 9)
    pdf.multi_cell(0, 5, "Note: Some metrics (e.g., Core Web Vitals, color contrast, HTTP/2 exact ALPN) "
                         "require client-side or network-layer measurements. We use conservative server-side heuristics to approximate impact.")

    return pdf.output(dest="S").encode("latin-1")

@app.post("/download")
async def download(req: Request):
    report_data = await req.json()
    try:
        pdf_bytes = build_pdf(report_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf",
                             headers={"Content-Disposition": "attachment; filename=FFTech_Elite_Audit.pdf"})

# (Optional) Health route
@app.get("/")
def health():
    return {"status": "FF TECH ELITE backend is running.", "endpoints": ["/audit", "/download"]}
