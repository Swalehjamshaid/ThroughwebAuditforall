
from urllib.parse import urlparse, urljoin
from typing import Dict, Any, Tuple
import re, time, ssl
try:
    import requests
except Exception:
    requests = None
import urllib.request

USER_AGENT = "FFTech-AuditBot/1.0 (+https://fftech.ai)"

# --- Build descriptors 1..200 ---
METRIC_DESCRIPTORS: Dict[int, Dict[str, str]] = {}
_idx = 1
for _category, _items in [
    ("Executive Summary & Grading", [
        "Overall Site Health Score (%)","Website Grade (A+ to D)","Executive Summary (200 Words)",
        "Strengths Highlight Panel","Weak Areas Highlight Panel","Priority Fixes Panel",
        "Visual Severity Indicators","Category Score Breakdown","Industry-Standard Presentation",
        "Print / Certified Export Readiness"
    ]),
    ("Overall Site Health", [
        "Site Health Score","Total Errors","Total Warnings","Total Notices","Total Crawled Pages",
        "Total Indexed Pages","Issues Trend","Crawl Budget Efficiency","Orphan Pages Percentage","Audit Completion Status"
    ]),
    ("Crawlability & Indexation", [
        "HTTP 2xx Pages","HTTP 3xx Pages","HTTP 4xx Pages","HTTP 5xx Pages","Redirect Chains","Redirect Loops",
        "Broken Internal Links","Broken External Links","robots.txt Blocked URLs","Meta Robots Blocked URLs",
        "Non-Canonical Pages","Missing Canonical Tags","Incorrect Canonical Tags","Sitemap Missing Pages",
        "Sitemap Not Crawled Pages","Hreflang Errors","Hreflang Conflicts","Pagination Issues","Crawl Depth Distribution",
        "Duplicate Parameter URLs"
    ]),
    ("On-page SEO", [
        "Missing Title Tags","Duplicate Title Tags","Title Too Long","Title Too Short","Missing Meta Descriptions",
        "Duplicate Meta Descriptions","Meta Too Long","Meta Too Short","Missing H1","Multiple H1","Duplicate Headings",
        "Thin Content Pages","Duplicate Content Pages","Low Text-to-HTML Ratio","Missing Image Alt Tags","Duplicate Alt Tags",
        "Large Uncompressed Images","Pages Without Indexed Content","Missing Structured Data","Structured Data Errors",
        "Rich Snippet Warnings","Missing Open Graph Tags","Long URLs","Uppercase URLs","Non-SEO-Friendly URLs",
        "Too Many Internal Links","Pages Without Incoming Links","Orphan Pages","Broken Anchor Links","Redirected Internal Links",
        "NoFollow Internal Links","Link Depth Issues","External Links Count","Broken External Links","Anchor Text Issues"
    ]),
    ("Performance & Technical", [
        "Largest Contentful Paint (LCP)","First Contentful Paint (FCP)","Cumulative Layout Shift (CLS)","Total Blocking Time",
        "First Input Delay","Speed Index","Time to Interactive","DOM Content Loaded","Total Page Size","Requests Per Page",
        "Unminified CSS","Unminified JavaScript","Render Blocking Resources","Excessive DOM Size","Third-Party Script Load",
        "Server Response Time","Image Optimization","Lazy Loading Issues","Browser Caching Issues","Missing GZIP / Brotli",
        "Resource Load Errors"
    ]),
    ("Mobile, Security & International", [
        "Mobile Friendly Test","Viewport Meta Tag","Small Font Issues","Tap Target Issues","Mobile Core Web Vitals",
        "Mobile Layout Issues","Intrusive Interstitials","Mobile Navigation Issues","HTTPS Implementation","SSL Certificate Validity",
        "Expired SSL","Mixed Content","Insecure Resources","Missing Security Headers","Open Directory Listing",
        "Login Pages Without HTTPS","Missing Hreflang","Incorrect Language Codes","Hreflang Conflicts","Region Targeting Issues",
        "Multi-Domain SEO Issues","Domain Authority","Referring Domains","Total Backlinks","Toxic Backlinks","NoFollow Backlinks",
        "Anchor Distribution","Referring IPs","Lost / New Backlinks","JavaScript Rendering Issues","CSS Blocking","Crawl Budget Waste",
        "AMP Issues","PWA Issues","Canonical Conflicts","Subdomain Duplication","Pagination Conflicts","Dynamic URL Issues",
        "Lazy Load Conflicts","Sitemap Presence","Noindex Issues","Structured Data Consistency","Redirect Correctness",
        "Broken Rich Media","Social Metadata Presence","Error Trend","Health Trend","Crawl Trend","Index Trend",
        "Core Web Vitals Trend","Backlink Trend","Keyword Trend","Historical Comparison","Overall Stability Index"
    ]),
    ("Competitor Analysis", [
        "Competitor Health Score","Competitor Performance Comparison","Competitor Core Web Vitals Comparison",
        "Competitor SEO Issues Comparison","Competitor Broken Links Comparison","Competitor Authority Score",
        "Competitor Backlink Growth","Competitor Keyword Visibility","Competitor Rank Distribution","Competitor Content Volume",
        "Competitor Speed Comparison","Competitor Mobile Score","Competitor Security Score","Competitive Gap Score",
        "Competitive Opportunity Heatmap","Competitive Risk Heatmap","Overall Competitive Rank"
    ]),
    ("Broken Links Intelligence", [
        "Total Broken Links","Internal Broken Links","External Broken Links","Broken Links Trend","Broken Pages by Impact",
        "Status Code Distribution","Page Type Distribution","Fix Priority Score","SEO Loss Impact","Affected Pages Count",
        "Broken Media Links","Resolution Progress","Risk Severity Index"
    ]),
    ("Opportunities, Growth & ROI", [
        "High Impact Opportunities","Quick Wins Score","Long-Term Fixes","Traffic Growth Forecast","Ranking Growth Forecast",
        "Conversion Impact Score","Content Expansion Opportunities","Internal Linking Opportunities","Speed Improvement Potential",
        "Mobile Improvement Potential","Security Improvement Potential","Structured Data Opportunities","Crawl Optimization Potential",
        "Backlink Opportunity Score","Competitive Gap ROI","Fix Roadmap Timeline","Time-to-Fix Estimate","Cost-to-Fix Estimate",
        "ROI Forecast","Overall Growth Readiness"
    ]),
]:
    for _name in _items:
        METRIC_DESCRIPTORS[_idx] = {"name": _name, "category": _category}
        _idx += 1

# --- helpers ---
def canonical_origin(url: str) -> str:
    p = urlparse(url)
    scheme = p.scheme or 'https'
    host = p.netloc or p.path.split('/')[0]
    return f"{scheme}://{host}".lower()

def _fetch(url: str, timeout: float = 12.0) -> Tuple[int, Dict[str, str], bytes, int, str]:
    start = time.time()
    status, headers, content, final_url = 0, {}, b'', url
    if requests:
        try:
            s = requests.Session(); s.headers.update({'User-Agent': USER_AGENT, 'Accept':'text/html,application/xhtml+xml'})
            r = s.get(url, timeout=timeout, allow_redirects=True)
            status = r.status_code; headers = {k.lower():v for k,v in r.headers.items()}; content = r.content or b''; final_url = str(r.url)
        except Exception:
            status = 0
    if status == 0:
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                status = getattr(resp, 'status', 200); headers = {k.lower():v for k,v in resp.getheaders()}; content = resp.read() or b''; final_url = resp.geturl()
        except Exception:
            status = 0
    elapsed_ms = int((time.time()-start)*1000)
    return status, headers, content, elapsed_ms, final_url

# --- main engine ---
class AuditEngine:
    def __init__(self, url: str):
        self.url = url

    def compute_metrics(self) -> Dict[int, Dict[str, Any]]:
        status, headers, content, ttfb_ms, final_url = _fetch(self.url)
        if status == 0 or not content:
            raise RuntimeError(f"Unable to fetch URL (status={status}). The site may block bots or require JS rendering.")
        html = content.decode('utf-8', errors='ignore')
        origin = canonical_origin(final_url)

        https_ok = final_url.startswith('https://')
        size_kb = len(content)//1024
        has_title = bool(re.search(r"<title\b[^>]*>.*?</title>", html, re.I|re.S))
        has_desc  = bool(re.search(r"<meta[^>]*name=['"]description['"][^>]*content=['"]", html, re.I))
        viewport  = bool(re.search(r"<meta[^>]*name=['"]viewport['"][^>]*>", html, re.I))
        has_h1    = bool(re.search(r"<h1\b", html, re.I))
        images_with_alt = len(re.findall(r"<img\b[^>]*\salt=['"]", html, re.I))
        total_images    = len(re.findall(r"<img\b", html, re.I))
        alt_ratio = (images_with_alt/total_images) if total_images>0 else 1.0
        structured_ld  = 'application/ld+json' in html.lower()
        open_graph     = bool(re.search(r"<meta[^>]*property=['"]og:", html, re.I))
        canonical_tag  = bool(re.search(r"<link[^>]*rel=['"]canonical['"][^>]*>", html, re.I))
        meta_robots_noindex = bool(re.search(r"<meta[^>]*name=['"]robots['"][^>]*content=['"][^>]*noindex", html, re.I))
        mixed_content  = (https_ok and ('http://' in html))
        csp   = bool(headers.get('content-security-policy'))
        hsts  = bool(headers.get('strict-transport-security'))
        xfo   = bool(headers.get('x-frame-options'))
        refpol= bool(headers.get('referrer-policy'))
        cc    = headers.get('cache-control','')
        m_age = re.search(r"max-age\s*=\s*(\d+)", cc, re.I)
        cache_max_age = int(m_age.group(1)) if m_age else 0

        # HEAD checks
        def _head_exists(path: str) -> bool:
            url = urljoin(origin, path)
            if requests:
                try:
                    r = requests.head(url, headers={'User-Agent': USER_AGENT}, timeout=6, allow_redirects=True)
                    return r.status_code < 400
                except Exception:
                    pass
            try:
                req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': USER_AGENT})
                with urllib.request.urlopen(req, timeout=6):
                    return True
            except Exception:
                return False
        sitemap = _head_exists('/sitemap.xml')
        robots  = _head_exists('/robots.txt')

        # Category scores (weighted)
        sec = 100
        if not https_ok: sec -= 40
        for flag, penalty in [(csp,10),(hsts,8),(xfo,6),(refpol,4)]:
            if not flag: sec -= penalty
        if mixed_content: sec -= 15
        sec = max(0, sec)

        perf = 100
        if ttfb_ms > 800: perf -= 25
        elif ttfb_ms > 400: perf -= 15
        elif ttfb_ms > 200: perf -= 8
        if size_kb > 1500: perf -= 25
        elif size_kb > 800: perf -= 15
        elif size_kb > 400: perf -= 8
        if cache_max_age >= 86400: perf += 5
        elif cache_max_age >= 3600: perf += 2
        perf = max(0, min(100, perf))

        seo = 60
        seo += 12 if has_title else -6
        seo += 12 if has_desc else -6
        seo += 8 if sitemap else -4
        seo += 6 if robots else -3
        seo += 12 if structured_ld else -6
        seo += 6 if canonical_tag else -3
        seo = max(0, min(100, seo))

        mobile = 70
        mobile += 15 if viewport else -10
        mobile += 5 if alt_ratio >= 0.9 else -3
        mobile = max(0, min(100, mobile))

        content = 70
        content += 10 if has_h1 else -5
        content += 8 if alt_ratio >= 0.9 else -4
        content += 6 if open_graph else -3
        content = max(0, min(100, content))

        overall = round(0.35*sec + 0.25*perf + 0.20*seo + 0.10*mobile + 0.10*content, 1)
        grade = ('A+' if overall>=95 else 'A' if overall>=85 else 'B' if overall>=75 else 'C' if overall>=65 else 'D')

        strengths = []
        if https_ok: strengths.append('HTTPS implementation is active.')
        if csp: strengths.append('Content-Security-Policy header present.')
        if hsts: strengths.append('HSTS enabled.')
        if viewport: strengths.append('Viewport meta is correctly configured.')
        if has_title and has_desc: strengths.append('Title and meta description present.')
        if structured_ld: strengths.append('Structured data (LD+JSON) detected.')
        if canonical_tag: strengths.append('Canonical tag present.')
        weaknesses = []
        if mixed_content: weaknesses.append('Mixed content detected under HTTPS.')
        if not csp: weaknesses.append('Missing Content-Security-Policy header.')
        if not hsts: weaknesses.append('HSTS header not found.')
        if not viewport: weaknesses.append('Missing mobile viewport meta tag.')
        if not has_title: weaknesses.append('Missing <title> tag.')
        if not has_desc: weaknesses.append('Missing meta description.')
        if alt_ratio < 0.9: weaknesses.append('Many images missing ALT text.')
        fixes = []
        if mixed_content: fixes.append('Fix mixed content: serve all assets via HTTPS.')
        if not csp: fixes.append('Add and harden Content-Security-Policy header.')
        if not hsts: fixes.append('Enable HSTS for transport security.')
        if not viewport: fixes.append("Add <meta name='viewport'> for mobile.")
        if not has_title or not has_desc: fixes.append('Provide meaningful title/meta description.')
        if alt_ratio < 0.9: fixes.append('Add ALT text to images for accessibility/SEO.')

        exec_summary = (
            f"Audited {final_url} for security, performance, SEO, mobile, and content signals. "
            f"Overall health {overall}% ({grade}). Security {sec}, Performance {perf}, SEO {seo}, Mobile {mobile}, Content {content}. "
            f"TTFB {ttfb_ms} ms; payload {size_kb} KB; caching max-age {cache_max_age}s. "
            f"Strengths: {', '.join(strengths) or '—'}. Weak areas: {', '.join(weaknesses) or '—'}. "
            f"Priority fixes: {', '.join(fixes) or '—'}. "
            f"For full crawl, backlinks, Core Web Vitals and competitor benchmarks, integrate APIs and internal crawlers."
        )

        metrics: Dict[int, Dict[str, Any]] = {}
        # 1..10 Executive Summary
        metrics[1]  = {"value": overall}
        metrics[2]  = {"value": grade}
        metrics[3]  = {"value": exec_summary}
        metrics[4]  = {"value": strengths}
        metrics[5]  = {"value": weaknesses}
        metrics[6]  = {"value": fixes}
        metrics[7]  = {"value": 'low' if overall>=80 else 'medium' if overall>=60 else 'high'}
        metrics[8]  = {"value": {"security": sec, "performance": perf, "seo": seo, "mobile": mobile, "content": content}}
        metrics[9]  = {"value": True}
        metrics[10] = {"value": True}

        # 11..20 Overall Site Health
        errors = 0
        warnings = int(not viewport) + int(not has_title) + int(not has_desc) + int(alt_ratio<0.9) + int(mixed_content)
        notices = 0
        metrics[11] = {"value": overall}
        metrics[12] = {"value": errors}
        metrics[13] = {"value": warnings}
        metrics[14] = {"value": notices}
        metrics[15] = {"value": 1}
        metrics[16] = {"value": 'N/A'}
        metrics[17] = {"value": 'N/A'}
        metrics[18] = {"value": 'N/A'}
        metrics[19] = {"value": 'N/A'}
        metrics[20] = {"value": 'completed'}

        # 21..40 Crawlability (placeholders + some booleans)
        for i in range(21, 41):
            metrics[i] = {"value": 'N/A'}
        metrics[34] = {"value": 'N/A'}
        metrics[35] = {"value": 'N/A'}

        # 41..75 On-page SEO
        metrics[41] = {"value": not has_title}
        metrics[45] = {"value": not has_desc}
        metrics[49] = {"value": not has_h1}
        metrics[55] = {"value": alt_ratio<0.9}
        metrics[59] = {"value": not structured_ld}
        metrics[62] = {"value": not open_graph}
        metrics[63] = {"value": len(final_url)>100}
        metrics[64] = {"value": bool(re.search(r"https?://[^/\s]*[A-Z]", final_url))}
        metrics[65] = {"value": bool(re.search(r"[\s\?%#]", final_url))}
        for i in range(41, 76):
            metrics.setdefault(i, {"value": 'N/A'})

        # 76..96 Performance & Technical
        metrics[84] = {"value": size_kb}
        metrics[91] = {"value": ttfb_ms}
        metrics[94] = {"value": cache_max_age>=3600}
        for i in range(76, 97):
            metrics.setdefault(i, {"value": 'N/A'})

        # 97..150 Mobile, Security & International
        metrics[98]  = {"value": viewport}
        metrics[105] = {"value": https_ok}
        metrics[110] = {"value": not (csp and hsts and xfo and refpol)}
        metrics[112] = {"value": not https_ok}
        metrics[136] = {"value": sitemap}
        metrics[137] = {"value": meta_robots_noindex}
        for i in range(97, 151):
            metrics.setdefault(i, {"value": 'N/A'})

        # 151..167 Competitor (N/A)
        for i in range(151, 168):
            metrics[i] = {"value": 'N/A'}

        # 168..180 Broken Links (N/A)
        for i in range(168, 181):
            metrics[i] = {"value": 'N/A'}

        # 181..200 Opportunities (partial)
        metrics[182] = {"value": 50 if overall<80 else 75}
        metrics[187] = {"value": ["Improve meta tags","Add ALT text","Reduce payload size"]}
        for i in range(181, 201):
            metrics.setdefault(i, {"value": 'N/A'})

        # expose counters as 100..102
        metrics[100] = {"value": errors}
        metrics[101] = {"value": warnings}
        metrics[102] = {"value": notices}

        return metrics


def grade_from_score(score: float) -> str:
    return ('A+' if score>=95 else 'A' if score>=85 else 'B' if score>=75 else 'C' if score>=65 else 'D')

def aggregate_score(_: Dict[str, Dict[str, Any]]):
    return 0.0, {}
