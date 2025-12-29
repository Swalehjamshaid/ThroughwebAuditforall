
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

# === Metric Descriptors ===
METRIC_DESCRIPTORS: Dict[int, Dict[str, str]] = {}
idx = 1
for category, items in [
    ("Executive Summary & Grading", ["Overall Site Health Score (%)","Website Grade (A+ to D)","Executive Summary (200 Words)",
                                     "Strengths Highlight Panel","Weak Areas Highlight Panel","Priority Fixes Panel",
                                     "Visual Severity Indicators","Category Score Breakdown","Industry-Standard Presentation",
                                     "Print / Certified Export Readiness"]),
    ("Overall Site Health", ["Site Health Score","Total Errors","Total Warnings","Total Notices","Total Crawled Pages",
                             "Total Indexed Pages","Issues Trend","Crawl Budget Efficiency","Orphan Pages Percentage","Audit Completion Status"]),
    ("Crawlability & Indexation", ["HTTP 2xx Pages","HTTP 3xx Pages","HTTP 4xx Pages","HTTP 5xx Pages","Redirect Chains","Redirect Loops",
                                   "Broken Internal Links","Broken External Links","robots.txt Blocked URLs","Meta Robots Blocked URLs",
                                   "Non-Canonical Pages","Missing Canonical Tags","Incorrect Canonical Tags","Sitemap Missing Pages",
                                   "Sitemap Not Crawled Pages","Hreflang Errors","Hreflang Conflicts","Pagination Issues","Crawl Depth Distribution",
                                   "Duplicate Parameter URLs"]),
    ("On-page SEO", ["Missing Title Tags","Duplicate Title Tags","Title Too Long","Title Too Short","Missing Meta Descriptions",
                     "Duplicate Meta Descriptions","Meta Too Long","Meta Too Short","Missing H1","Multiple H1","Duplicate Headings",
                     "Thin Content Pages","Duplicate Content Pages","Low Text-to-HTML Ratio","Missing Image Alt Tags","Duplicate Alt Tags",
                     "Large Uncompressed Images","Pages Without Indexed Content","Missing Structured Data","Structured Data Errors",
                     "Rich Snippet Warnings","Missing Open Graph Tags","Long URLs","Uppercase URLs","Non-SEO-Friendly URLs",
                     "Too Many Internal Links","Pages Without Incoming Links","Orphan Pages","Broken Anchor Links","Redirected Internal Links",
                     "NoFollow Internal Links","Link Depth Issues","External Links Count","Broken External Links","Anchor Text Issues"]),
    ("Performance & Technical", ["Largest Contentful Paint (LCP)","First Contentful Paint (FCP)","Cumulative Layout Shift (CLS)","Total Blocking Time",
                                 "First Input Delay","Speed Index","Time to Interactive","DOM Content Loaded","Total Page Size","Requests Per Page",
                                 "Unminified CSS","Unminified JavaScript","Render Blocking Resources","Excessive DOM Size","Third-Party Script Load",
                                 "Server Response Time","Image Optimization","Lazy Loading Issues","Browser Caching Issues","Missing GZIP / Brotli",
                                 "Resource Load Errors"]),
    ("Mobile, Security & International", ["Mobile Friendly Test","Viewport Meta Tag","Small Font Issues","Tap Target Issues","Mobile Core Web Vitals",
                                          "Mobile Layout Issues","Intrusive Interstitials","Mobile Navigation Issues","HTTPS Implementation","SSL Certificate Validity",
                                          "Expired SSL","Mixed Content","Insecure Resources","Missing Security Headers","Open Directory Listing",
                                          "Login Pages Without HTTPS","Missing Hreflang","Incorrect Language Codes","Hreflang Conflicts","Region Targeting Issues",
                                          "Multi-Domain SEO Issues","Domain Authority","Referring Domains","Total Backlinks","Toxic Backlinks","NoFollow Backlinks",
                                          "Anchor Distribution","Referring IPs","Lost / New Backlinks","JavaScript Rendering Issues","CSS Blocking","Crawl Budget Waste",
                                          "AMP Issues","PWA Issues","Canonical Conflicts","Subdomain Duplication","Pagination Conflicts","Dynamic URL Issues",
                                          "Lazy Load Conflicts","Sitemap Presence","Noindex Issues","Structured Data Consistency","Redirect Correctness",
                                          "Broken Rich Media","Social Metadata Presence","Error Trend","Health Trend","Crawl Trend","Index Trend",
                                          "Core Web Vitals Trend","Backlink Trend","Keyword Trend","Historical Comparison","Overall Stability Index"]),
    ("Competitor Analysis", ["Competitor Health Score","Competitor Performance Comparison","Competitor Core Web Vitals Comparison",
                             "Competitor SEO Issues Comparison","Competitor Broken Links Comparison","Competitor Authority Score",
                             "Competitor Backlink Growth","Competitor Keyword Visibility","Competitor Rank Distribution","Competitor Content Volume",
                             "Competitor Speed Comparison","Competitor Mobile Score","Competitor Security Score","Competitive Gap Score",
                             "Competitive Opportunity Heatmap","Competitive Risk Heatmap","Overall Competitive Rank"]),
    ("Broken Links Intelligence", ["Total Broken Links","Internal Broken Links","External Broken Links","Broken Links Trend","Broken Pages by Impact",
                                   "Status Code Distribution","Page Type Distribution","Fix Priority Score","SEO Loss Impact","Affected Pages Count",
                                   "Broken Media Links","Resolution Progress","Risk Severity Index"]),
    ("Opportunities, Growth & ROI", ["High Impact Opportunities","Quick Wins Score","Long-Term Fixes","Traffic Growth Forecast","Ranking Growth Forecast",
                                     "Conversion Impact Score","Content Expansion Opportunities","Internal Linking Opportunities","Speed Improvement Potential",
                                     "Mobile Improvement Potential","Security Improvement Potential","Structured Data Opportunities","Crawl Optimization Potential",
                                     "Backlink Opportunity Score","Competitive Gap ROI","Fix Roadmap Timeline","Time-to-Fix Estimate","Cost-to-Fix Estimate",
                                     "ROI Forecast","Overall Growth Readiness"]),
]:
    for name in items:
        METRIC_DESCRIPTORS[idx] = {"name": name, "category": category}
        idx += 1

# === Scoring ===
WEIGHTS = {"security": 0.35, "performance": 0.25, "seo": 0.20, "mobile": 0.10, "content": 0.10}
SECURITY_PENALTIES = {"csp": 20, "hsts": 15, "x_frame": 10, "referrer_policy": 5}

def canonical_origin(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme or 'https'
    host = parsed.netloc or parsed.path.split('/')[0]
    return f"{scheme}://{host}".lower()

def clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))

def grade_from_score(score: float) -> str:
    s = round(score)
    if s >= 90: return 'A'
    if s >= 80: return 'B'
    if s >= 70: return 'C'
    if s >= 60: return 'D'
    return 'F'

# === Fetching ===
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

# === Category Scoring ===
def compute_category_security(sec: Dict[str, Any]) -> float:
    base = 100 if sec.get('https_enabled') else 60
    for k, penalty in SECURITY_PENALTIES.items():
        if not sec.get(k, False):
            base -= penalty
    return clamp(base)

def compute_category_performance(perf: Dict[str, Any]) -> float:
    score = 100
    ttfb = perf.get('ttfb_ms', 0)
    size = perf.get('payload_kb', 0)
    cache = perf.get('cache_max_age_s', 0)
    if ttfb > 800: score -= 25
    elif ttfb > 400: score -= 15
    elif ttfb > 200: score -= 8
    if size > 1500: score -= 25
    elif size > 800: score -= 15
    elif size > 400: score -= 8
    if cache >= 86400: score += 5
    elif cache >= 3600: score += 2
    return clamp(score)

def compute_category_seo(seo: Dict[str, Any]) -> float:
    score = 60
    score += 12 if seo.get('has_title') else -6
    score += 12 if seo.get('has_meta_desc') else -6
    score += 8 if seo.get('has_sitemap') else -4
    score += 6 if seo.get('has_robots') else -3
    score += 12 if seo.get('structured_data_ok') else -6
    return clamp(score)

def compute_category_mobile(m: Dict[str, Any]) -> float:
    score = 70
    score += 15 if m.get('viewport_ok') else -10
    score += 10 if m.get('responsive_meta') else -6
    return clamp(score)

def compute_category_content(c: Dict[str, Any]) -> float:
    score = 70
    score += 10 if c.get('has_h1') else -5
    score += 10 if c.get('alt_ok') else -5
    return clamp(score)

def aggregate_score(metrics: Dict[str, Dict[str, Any]]) -> Tuple[float, Dict[str, float]]:
    cats: Dict[str, float] = {}
    cats['security'] = compute_category_security(metrics.get('security', {}))
    cats['performance'] = compute_category_performance(metrics.get('performance', {}))
    cats['seo'] = compute_category_seo(metrics.get('seo', {}))
    cats['mobile'] = compute_category_mobile(metrics.get('mobile', {}))
    cats['content'] = compute_category_content(metrics.get('content', {}))
    total = sum(WEIGHTS[k] * cats[k] for k in WEIGHTS)
    return round(clamp(total), 1), cats

# === Audit Engine ===
class AuditEngine:
    def __init__(self, url: str):
        self.url = url

    def compute_metrics(self) -> Dict[int, Dict[str, Any]]:
        origin = canonical_origin(self.url)
        r = fetch(origin)
        headers = r.headers
        content = r.content
        html_text = content.decode('utf-8', errors='ignore') if content else ''

        # Security
        sec = {
            'https_enabled': origin.startswith('https://'),
            'csp': bool(headers.get('content-security-policy')),
            'hsts': bool(headers.get('strict-transport-security')),
            'x_frame': bool(headers.get('x-frame-options')),
            'referrer_policy': bool(headers.get('referrer-policy')),
        }

        # Performance
        cache_max_age = 0
        cc = headers.get('cache-control', '')
        m = re.search(r'max-age\s*=\s*(\d+)', cc, re.I)
        if m:
            cache_max_age = int(m.group(1))
        perf = {
            'ttfb_ms': r.elapsed_ms,
            'payload_kb': int(len(content) / 1024) if content else 0,
            'cache_max_age_s': cache_max_age,
        }

        # SEO (✅ corrected regexes: use real < and >, proper quoting)
        has_title = bool(re.search(r'<title\b[^>]*>.*?</title>', html_text, re.I | re.S))
        has_desc  = bool(re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']', html_text, re.I))
        has_sitemap = head_exists(origin, '/sitemap.xml')
        has_robots  = head_exists(origin, '/robots.txt')
        structured  = 'application/ld+json' in html_text.lower()
        seo = {
            'has_title': has_title,
            'has_meta_desc': has_desc,
            'has_sitemap': has_sitemap,
            'has_robots': has_robots,
            'structured_data_ok': structured,
        }

        # Mobile (✅ corrected regex)
        viewport   = bool(re.search(r'<meta[^>]*name=["\']viewport["\'][^>]*>', html_text, re.I))
        responsive = 'device-width' in html_text.lower()
        mobile = {'viewport_ok': viewport, 'responsive_meta': responsive}

        # Content (✅ corrected regex)
        has_h1 = bool(re.search(r'<h1\b', html_text, re.I))
        alt_ok = bool(re.search(r'<img\b[^>]*\salt=["\']', html_text, re.I))
        content_cat = {'has_h1': has_h1, 'alt_ok': alt_ok}

        # Populate metrics
        metrics: Dict[int, Dict[str, Any]] = {}
        metrics[10] = {'value': sec['https_enabled']}
        metrics[11] = {'value': sec['csp']}
        metrics[12] = {'value': sec['hsts']}
        metrics[13] = {'value': sec['x_frame']}
        metrics[14] = {'value': sec['referrer_policy']}
        metrics[20] = {'value': perf['ttfb_ms']}
        metrics[21] = {'value': perf['payload_kb']}
        metrics[22] = {'value': perf['cache_max_age_s']}
        metrics[30] = {'value': seo['has_title']}
        metrics[31] = {'value': seo['has_meta_desc']}
        metrics[32] = {'value': seo['has_sitemap']}
        metrics[33] = {'value': seo['has_robots']}
        metrics[34] = {'value': seo['structured_data_ok']}
        metrics[40] = {'value': mobile['viewport_ok']}
        metrics[41] = {'value': mobile['responsive_meta']}
        metrics[50] = {'value': content_cat['has_h1']}
        metrics[51] = {'value': content_cat['alt_ok']}

        # Severity (simple example)
        warnings = sum(1 for k in ['csp','hsts','x_frame','referrer_policy'] if not sec[k])
        metrics[100] = {'value': 0}  # errors
        metrics[101] = {'value': warnings}
        metrics[102] = {'value': 0}  # notices

        return metrics
