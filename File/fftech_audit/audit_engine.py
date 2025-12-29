
# fftech_audit/audit_engine.py
from urllib.parse import urlparse, urljoin
from typing import Dict, Any, List, Tuple
import re, time, math, ssl
try:
    import requests
except Exception:
    requests = None
import urllib.request

USER_AGENT = "FFTech-AuditBot/1.0 (+https://fftech.ai)"

# ----------------------------
# Metric Descriptors (1..200)
# ----------------------------
METRIC_DESCRIPTORS: Dict[int, Dict[str, str]] = {}
_idx = 1
for _category, _items in [
    ("Executive Summary & Grading", [
        "Overall Site Health Score (%)", "Website Grade (A+ to D)", "Executive Summary (200 Words)",
        "Strengths Highlight Panel", "Weak Areas Highlight Panel", "Priority Fixes Panel",
        "Visual Severity Indicators", "Category Score Breakdown", "Industry-Standard Presentation",
        "Print / Certified Export Readiness"
    ]),
    ("Overall Site Health", [
        "Site Health Score", "Total Errors", "Total Warnings", "Total Notices", "Total Crawled Pages",
        "Total Indexed Pages", "Issues Trend", "Crawl Budget Efficiency", "Orphan Pages Percentage", "Audit Completion Status"
    ]),
    ("Crawlability & Indexation", [
        "HTTP 2xx Pages", "HTTP 3xx Pages", "HTTP 4xx Pages", "HTTP 5xx Pages", "Redirect Chains", "Redirect Loops",
        "Broken Internal Links", "Broken External Links", "robots.txt Blocked URLs", "Meta Robots Blocked URLs",
        "Non-Canonical Pages", "Missing Canonical Tags", "Incorrect Canonical Tags", "Sitemap Missing Pages",
        "Sitemap Not Crawled Pages", "Hreflang Errors", "Hreflang Conflicts", "Pagination Issues", "Crawl Depth Distribution",
        "Duplicate Parameter URLs"
    ]),
    ("On-page SEO", [
        "Missing Title Tags", "Duplicate Title Tags", "Title Too Long", "Title Too Short", "Missing Meta Descriptions",
        "Duplicate Meta Descriptions", "Meta Too Long", "Meta Too Short", "Missing H1", "Multiple H1", "Duplicate Headings",
        "Thin Content Pages", "Duplicate Content Pages", "Low Text-to-HTML Ratio", "Missing Image Alt Tags", "Duplicate Alt Tags",
        "Large Uncompressed Images", "Pages Without Indexed Content", "Missing Structured Data", "Structured Data Errors",
        "Rich Snippet Warnings", "Missing Open Graph Tags", "Long URLs", "Uppercase URLs", "Non-SEO-Friendly URLs",
        "Too Many Internal Links", "Pages Without Incoming Links", "Orphan Pages", "Broken Anchor Links", "Redirected Internal Links",
        "NoFollow Internal Links", "Link Depth Issues", "External Links Count", "Broken External Links", "Anchor Text Issues"
    ]),
    ("Performance & Technical", [
        "Largest Contentful Paint (LCP)", "First Contentful Paint (FCP)", "Cumulative Layout Shift (CLS)", "Total Blocking Time",
        "First Input Delay", "Speed Index", "Time to Interactive", "DOM Content Loaded", "Total Page Size", "Requests Per Page",
        "Unminified CSS", "Unminified JavaScript", "Render Blocking Resources", "Excessive DOM Size", "Third-Party Script Load",
        "Server Response Time", "Image Optimization", "Lazy Loading Issues", "Browser Caching Issues", "Missing GZIP / Brotli",
        "Resource Load Errors"
    ]),
    ("Mobile, Security & International", [
        "Mobile Friendly Test", "Viewport Meta Tag", "Small Font Issues", "Tap Target Issues", "Mobile Core Web Vitals",
        "Mobile Layout Issues", "Intrusive Interstitials", "Mobile Navigation Issues", "HTTPS Implementation", "SSL Certificate Validity",
        "Expired SSL", "Mixed Content", "Insecure Resources", "Missing Security Headers", "Open Directory Listing",
        "Login Pages Without HTTPS", "Missing Hreflang", "Incorrect Language Codes", "Hreflang Conflicts", "Region Targeting Issues",
        "Multi-Domain SEO Issues", "Domain Authority", "Referring Domains", "Total Backlinks", "Toxic Backlinks", "NoFollow Backlinks",
        "Anchor Distribution", "Referring IPs", "Lost / New Backlinks", "JavaScript Rendering Issues", "CSS Blocking", "Crawl Budget Waste",
        "AMP Issues", "PWA Issues", "Canonical Conflicts", "Subdomain Duplication", "Pagination Conflicts", "Dynamic URL Issues",
        "Lazy Load Conflicts", "Sitemap Presence", "Noindex Issues", "Structured Data Consistency", "Redirect Correctness",
        "Broken Rich Media", "Social Metadata Presence", "Error Trend", "Health Trend", "Crawl Trend", "Index Trend",
        "Core Web Vitals Trend", "Backlink Trend", "Keyword Trend", "Historical Comparison", "Overall Stability Index"
    ]),
    ("Competitor Analysis", [
        "Competitor Health Score", "Competitor Performance Comparison", "Competitor Core Web Vitals Comparison",
        "Competitor SEO Issues Comparison", "Competitor Broken Links Comparison", "Competitor Authority Score",
        "Competitor Backlink Growth", "Competitor Keyword Visibility", "Competitor Rank Distribution", "Competitor Content Volume",
        "Competitor Speed Comparison", "Competitor Mobile Score", "Competitor Security Score", "Competitive Gap Score",
        "Competitive Opportunity Heatmap", "Competitive Risk Heatmap", "Overall Competitive Rank"
    ]),
    ("Broken Links Intelligence", [
        "Total Broken Links", "Internal Broken Links", "External Broken Links", "Broken Links Trend", "Broken Pages by Impact",
        "Status Code Distribution", "Page Type Distribution", "Fix Priority Score", "SEO Loss Impact", "Affected Pages Count",
        "Broken Media Links", "Resolution Progress", "Risk Severity Index"
    ]),
    ("Opportunities, Growth & ROI", [
        "High Impact Opportunities", "Quick Wins Score", "Long-Term Fixes", "Traffic Growth Forecast", "Ranking Growth Forecast",
        "Conversion Impact Score", "Content Expansion Opportunities", "Internal Linking Opportunities", "Speed Improvement Potential",
        "Mobile Improvement Potential", "Security Improvement Potential", "Structured Data Opportunities", "Crawl Optimization Potential",
        "Backlink Opportunity Score", "Competitive Gap ROI", "Fix Roadmap Timeline", "Time-to-Fix Estimate", "Cost-to-Fix Estimate",
        "ROI Forecast", "Overall Growth Readiness"
    ]),
]:
    for _name in _items:
        METRIC_DESCRIPTORS[_idx] = {"name": _name, "category": _category}
        _idx += 1

# ----------------------------
# Helpers
# ----------------------------
def canonical_origin(url: str) -> str:
    p = urlparse(url)
    scheme = p.scheme or "https"
    host = p.netloc or p.path.split("/")[0]
    return f"{scheme}://{host}".lower()

def _fetch(url: str, timeout: float = 12.0) -> Tuple[int, Dict[str, str], bytes, int, str]:
    start = time.time()
    status, headers, content, final_url = 0, {}, b"", url

    if requests:
        try:
            s = requests.Session()
            s.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
            r = s.get(url, timeout=timeout, allow_redirects=True)
            status = r.status_code
            headers = {k.lower(): v for k, v in r.headers.items()}
            content = r.content or b""
            final_url = str(r.url)
        except Exception:
            status = 0

    if status == 0:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                status = getattr(resp, "status", 200)
                headers = {k.lower(): v for k, v in resp.getheaders()}
                content = resp.read() or b""
                final_url = resp.geturl()
        except Exception:
            status = 0

    elapsed_ms = int((time.time() - start) * 1000)
    return status, headers, content, elapsed_ms, final_url

def _grade_a_plus_to_d(score: float) -> str:
    s = round(score)
    if s >= 95: return "A+"
    if s >= 85: return "A"
    if s >= 75: return "B"
    if s >= 65: return "C"
    return "D"

# ----------------------------
# Core Engine
# ----------------------------
class AuditEngine:
    def __init__(self, url: str):
        self.url = url

    def compute_metrics(self) -> Dict[int, Dict[str, Any]]:
        target_url = self.url.strip()
        status, headers, content, ttfb_ms, final_url = _fetch(target_url)

        if status == 0 or not content:
            raise RuntimeError(f"Unable to fetch URL (status={status}). The site may block bots or require JS rendering.")

        html = content.decode("utf-8", errors="ignore")
        origin = canonical_origin(target_url)

        # ---- fast checks
        https_enabled = target_url.startswith("https://")
        page_size_kb = len(content) // 1024
        has_title    = bool(re.search(r"<title\b[^>]*>.*?</title>", html, re.I | re.S))
        meta_desc    = bool(re.search(r"<meta[^>]*name=['\"]description['\"][^>]*content=['\"]", html, re.I))
        viewport_ok  = bool(re.search(r"<meta[^>]*name=['\"]viewport['\"][^>]*>", html, re.I))
        has_h1       = bool(re.search(r"<h1\b", html, re.I))
        images_with_alt = len(re.findall(r"<img\b[^>]*\salt=['\"]", html, re.I))
        total_images     = len(re.findall(r"<img\b", html, re.I))
        alt_ok_ratio     = (images_with_alt / total_images) if total_images > 0 else 1.0
        structured_ld    = "application/ld+json" in html.lower()
        open_graph       = bool(re.search(r"<meta[^>]*property=['\"]og:", html, re.I))
        canonical_tag    = bool(re.search(r"<link[^>]*rel=['\"]canonical['\"][^>]*>", html, re.I))
        meta_robots_noindex = bool(re.search(r"<meta[^>]*name=['\"]robots['\"][^>]*content=['\"][^>]*noindex", html, re.I))
        mixed_content    = (https_enabled and ("http://" in html))  # crude but useful
        csp              = bool(headers.get("content-security-policy"))
        hsts             = bool(headers.get("strict-transport-security"))
        x_frame          = bool(headers.get("x-frame-options"))
        ref_policy       = bool(headers.get("referrer-policy"))
        cache_control    = headers.get("cache-control", "")
        m_age            = re.search(r"max-age\s*=\s*(\d+)", cache_control, re.I)
        cache_max_age_s  = int(m_age.group(1)) if m_age else 0

        # origin-level presence
        sitemap_present  = self._head_exists(origin, "/sitemap.xml")
        robots_present   = self._head_exists(origin, "/robots.txt")

        # ---- category scores (simple demo)
        score_security = 100
        if not https_enabled: score_security -= 40
        for flag, penalty in [(csp, 10), (hsts, 8), (x_frame, 6), (ref_policy, 4)]:
            if not flag: score_security -= penalty
        if mixed_content: score_security -= 15
        score_security = max(0, score_security)

        score_perf = 100
        if ttfb_ms > 800: score_perf -= 25
        elif ttfb_ms > 400: score_perf -= 15
        elif ttfb_ms > 200: score_perf -= 8
        if page_size_kb > 1500: score_perf -= 25
        elif page_size_kb > 800: score_perf -= 15
        elif page_size_kb > 400: score_perf -= 8
        if cache_max_age_s >= 86400: score_perf += 5
        elif cache_max_age_s >= 3600: score_perf += 2
        score_perf = max(0, min(100, score_perf))

        score_seo = 60
        score_seo += 12 if has_title else -6
        score_seo += 12 if meta_desc else -6
        score_seo += 8 if sitemap_present else -4
        score_seo += 6 if robots_present else -3
        score_seo += 12 if structured_ld else -6
        score_seo += 6 if canonical_tag else -3
        score_seo = max(0, min(100, score_seo))

        score_mobile = 70
        score_mobile += 15 if viewport_ok else -10
        score_mobile += 5 if alt_ok_ratio >= 0.9 else -3
        score_mobile = max(0, min(100, score_mobile))

        score_content = 70
        score_content += 10 if has_h1 else -5
        score_content += 8 if alt_ok_ratio >= 0.9 else -4
        score_content += 6 if open_graph else -3
        score_content = max(0, min(100, score_content))

        # weighted overall
        overall = round(
            0.35 * score_security +
            0.25 * score_perf +
            0.20 * score_seo +
            0.10 * score_mobile +
            0.10 * score_content, 1
        )
        grade = _grade_a_plus_to_d(overall)

        # executive summary (approx ~180–220 words)
        strengths = []
        if https_enabled: strengths.append("HTTPS implementation is active.")
        if csp: strengths.append("Content-Security-Policy header is present.")
        if hsts: strengths.append("HSTS is enabled.")
        if viewport_ok: strengths.append("Mobile viewport is correctly configured.")
        if has_title and meta_desc: strengths.append("Title and meta description are present.")
        if structured_ld: strengths.append("Structured data (LD+JSON) detected.")
        if canonical_tag: strengths.append("Canonical tag is present.")
        weaknesses = []
        if mixed_content: weaknesses.append("Mixed content detected on HTTPS page.")
        if not csp: weaknesses.append("Missing Content-Security-Policy header.")
        if not hsts: weaknesses.append("HSTS header not found.")
        if not viewport_ok: weaknesses.append("Missing mobile viewport meta tag.")
        if not has_title: weaknesses.append("Missing <title> tag.")
        if not meta_desc: weaknesses.append("Missing meta description.")
        if alt_ok_ratio < 0.9: weaknesses.append("Many images missing ALT text.")
        priority_fixes = []
        if mixed_content: priority_fixes.append("Eliminate mixed content (load assets via HTTPS).")
        if not csp: priority_fixes.append("Add and harden CSP header.")
        if not hsts: priority_fixes.append("Enable HSTS for stronger transport security.")
        if not viewport_ok: priority_fixes.append("Add <meta name='viewport'> for mobile responsiveness.")
        if not has_title or not meta_desc: priority_fixes.append("Provide meaningful title and meta description.")
        if alt_ok_ratio < 0.9: priority_fixes.append("Add ALT text to images for accessibility/SEO.")

        exec_summary_text = (
            f"This FF Tech AI audit examined {final_url} to assess security, performance, SEO, mobile readiness, and content signals. "
            f"Overall site health scored {overall}% ({grade}). Security posture is {'strong' if score_security>=80 else 'moderate' if score_security>=60 else 'weak'}, "
            f"with HTTPS {'enabled' if https_enabled else 'disabled'}, CSP {'present' if csp else 'missing'}, and HSTS {'enabled' if hsts else 'absent'}. "
            f"Performance shows a TTFB of {ttfb_ms} ms and page payload of {page_size_kb} KB; caching directives suggest max-age={cache_max_age_s} seconds. "
            f"SEO essentials {'are' if (has_title and meta_desc) else 'are not'} in place; structured data is "
            f"{'detected' if structured_ld else 'absent'}. Mobile readiness is {'good' if viewport_ok else 'limited'} due to viewport meta "
            f"{'present' if viewport_ok else 'missing'}. Content quality indicators include H1 "
            f"{'found' if has_h1 else 'missing'} and image ALT coverage at {int(alt_ok_ratio*100)}%. "
            f"Key strengths: {', '.join(strengths) or '—'}. Key weaknesses: {', '.join(weaknesses) or '—'}. "
            f"Top priority fixes: {', '.join(priority_fixes) or '—'}. "
            f"Category scores — Security {score_security}, Performance {score_perf}, SEO {score_seo}, Mobile {score_mobile}, Content {score_content}. "
            f"This report reflects a single-page scan. For full crawlability, backlink depth, Core Web Vitals, and competitor benchmarks, "
            f"integrate connectors (Search Console, Lighthouse, backlink APIs) and internal crawlers."
        )

        # build metrics 1..200 (fill computed + placeholders)
        metrics: Dict[int, Dict[str, Any]] = {}

        # Executive Summary & Grading (1–10)
        metrics[1]  = {"value": overall}
        metrics[2]  = {"value": grade}
        metrics[3]  = {"value": exec_summary_text}
        metrics[4]  = {"value": strengths}
        metrics[5]  = {"value": weaknesses}
        metrics[6]  = {"value": priority_fixes}
        metrics[7]  = {"value": "low" if overall >= 80 else "medium" if overall >= 60 else "high"}
        metrics[8]  = {"value": {"security": score_security, "performance": score_perf, "seo": score_seo, "mobile": score_mobile, "content": score_content}}
        metrics[9]  = {"value": True}
        metrics[10] = {"value": True}  # assumes printable; PDF generator exists

        # Overall Site Health (11–20)
        errors = 0
        warnings = int((not viewport_ok)) + int((not has_title)) + int((not meta_desc)) + int(alt_ok_ratio < 0.9) + int(mixed_content)
        notices = 0
        metrics[11] = {"value": overall}
        metrics[12] = {"value": errors}
        metrics[13] = {"value": warnings}
        metrics[14] = {"value": notices}
        metrics[15] = {"value": 1}       # single page scan
        metrics[16] = {"value": "N/A"}   # requires search engine data
        metrics[17] = {"value": "N/A"}   # requires history
        metrics[18] = {"value": "N/A"}   # requires crawl
        metrics[19] = {"value": "N/A"}
        metrics[20] = {"value": "completed"}

        # Crawlability & Indexation (21–40) — placeholders + basic checks
        for mid in range(21, 41):
            metrics[mid] = {"value": "N/A"}
        metrics[34] = {"value": "N/A"}  # Sitemap missing pages (needs crawl)
        metrics[35] = {"value": "N/A"}  # Sitemap not crawled pages
        metrics[29] = {"value": "N/A"}  # robots.txt blocked URLs
        metrics[30] = {"value": "N/A"}  # meta robots blocked
        metrics[31] = {"value": "N/A"}
        metrics[32] = {"value": not canonical_tag}
        metrics[33] = {"value": False}  # incorrect canonical
        # override presence flags
        metrics[34] = {"value": "N/A"}
        metrics[35] = {"value": "N/A"}

        # On-page SEO (41–75)
        metrics[41] = {"value": not has_title}
        metrics[45] = {"value": not meta_desc}
        metrics[49] = {"value": not has_h1}
        metrics[55] = {"value": alt_ok_ratio < 0.9}
        metrics[59] = {"value": not structured_ld}
        metrics[62] = {"value": not open_graph}
        metrics[63] = {"value": len(final_url) > 100}
        metrics[64] = {"value": bool(re.search(r"https?://[^/\s]*[A-Z]", final_url))}
        metrics[65] = {"value": bool(re.search(r"[\s\?%#]", final_url))}
        # fill others as N/A
        for mid in range(41, 76):
            metrics.setdefault(mid, {"value": "N/A"})

        # Performance & Technical (76–96)
        metrics[84] = {"value": page_size_kb}
        metrics[91] = {"value": ttfb_ms}
        metrics[94] = {"value": cache_max_age_s >= 3600}
        for mid in range(76, 97):
            metrics.setdefault(mid, {"value": "N/A"})

        # Mobile, Security & International (97–150)
        metrics[98]  = {"value": viewport_ok}
        metrics[105] = {"value": https_enabled}
        metrics[110] = {"value": not (csp and hsts and x_frame and ref_policy)}  # missing any header
        metrics[111] = {"value": "N/A"}
        metrics[112] = {"value": not https_enabled}
        metrics[113] = {"value": "N/A"}  # hreflang
        metrics[136] = {"value": sitemap_present}
        metrics[137] = {"value": meta_robots_noindex}
        metrics[139] = {"value": "N/A"}  # redirect correctness
        metrics[141] = {"value": open_graph}
        for mid in range(97, 151):
            metrics.setdefault(mid, {"value": "N/A"})

        # Competitor Analysis (151–167) — placeholders
        for mid in range(151, 168):
            metrics[mid] = {"value": "N/A"}

        # Broken Links Intelligence (168–180) — placeholders
        for mid in range(168, 181):
            metrics[mid] = {"value": "N/A"}

        # Opportunities, Growth & ROI (181–200) — placeholders
        metrics[182] = {"value": 50 if overall < 80 else 75}  # Quick wins score (heuristic)
        metrics[187] = {"value": ["Improve meta tags", "Add ALT text", "Reduce payload size"]}
        metrics[189] = {"value": "N/A"}  # Speed improvement potential
        metrics[199] = {"value": "N/A"}  # ROI forecast
        metrics[200] = {"value": "N/A"}  # Overall growth readiness
        for mid in range(181, 201):
            metrics.setdefault(mid, {"value": "N/A"})

        # summary error/warning/notices counters (for UI if needed)
        metrics[100] = {"value": errors}
        metrics[101] = {"value": warnings}
        metrics[102] = {"value": notices}

        return metrics

    @staticmethod
    def _head_exists(base: str, path: str, timeout: float = 6.0) -> bool:
        url = urljoin(base, path)
        if requests:
            try:
                r = requests.head(url, headers={"User-Agent": USER_AGENT}, timeout=timeout, allow_redirects=True)
                return r.status_code < 400
            except Exception:
                pass
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout):
                return True
        except Exception:
            return False

def grade_from_score(score: float) -> str:
    return _grade_a_plus_to_d(score)

def aggregate_score(_: Dict[str, Dict[str, Any]]) -> Tuple[float, Dict[str, float]]:
    # kept for signature compatibility; your app now reads #1 and #8 directly
    return 0.0, {}
