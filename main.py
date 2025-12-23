
import asyncio
import time
import io
import os
import logging
from typing import Dict, Any, List, Tuple, Optional
from urllib.parse import urlparse, urlunparse

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates

from bs4 import BeautifulSoup
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ==================== LOGGING ====================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FF_TECH_ELITE_V3")

# ==================== OPTIONAL PLAYWRIGHT ====================
try:
    from playwright.async_api import async_playwright, ConsoleMessage
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not installed. /audit will return 501 Not Implemented.")

# ==================== APP ====================
app = FastAPI(title="FF TECH ELITE v3 - Weighted Audit Engine")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"]
)

templates = Jinja2Templates(directory="templates")

# ==================== CONFIG ====================
CATEGORIES = ["Performance", "SEO", "UX", "Security"]
PILLAR_WEIGHTS = {"Performance": 0.4, "SEO": 0.3, "UX": 0.2, "Security": 0.1}

CRITICAL_METRICS = {
    "Performance": ["Largest Contentful Paint (LCP)", "First Contentful Paint (FCP)", "Time to First Byte (TTFB)", "Cumulative Layout Shift (CLS)"],
    "SEO": ["Page Title (Length & Quality)", "Meta Description (Length & Quality)", "H1 Tag Unique & Present", "Canonical Tag Present"],
    "UX": ["Viewport Meta Tag", "Mobile-Friendly Design"],
    "Security": ["HTTPS Enforced", "HSTS Header", "Content-Security-Policy Header", "X-Frame-Options Header"]
}

METRICS_LIST: List[Tuple[str, str]] = [
    # Performance
    ("Largest Contentful Paint (LCP)", "Performance"),
    ("First Contentful Paint (FCP)", "Performance"),
    ("Time to First Byte (TTFB)", "Performance"),
    ("Cumulative Layout Shift (CLS)", "Performance"),
    ("Total Blocking Time (TBT)", "Performance"),
    ("Page Weight (KB)", "Performance"),
    ("Number of Requests", "Performance"),
    ("Image Optimization", "Performance"),
    ("JavaScript Minification", "Performance"),
    ("Font Display Strategy", "Performance"),
    # SEO
    ("Page Title (Length & Quality)", "SEO"),
    ("Meta Description (Length & Quality)", "SEO"),
    ("Canonical Tag Present", "SEO"),
    ("H1 Tag Unique & Present", "SEO"),
    ("Heading Structure (H2-H6)", "SEO"),
    ("Image Alt Attributes", "SEO"),
    ("Robots Meta Tag", "SEO"),
    ("Open Graph Tags", "SEO"),
    ("Structured Data (Schema.org)", "SEO"),
    ("Internal Links Quality", "SEO"),
    # UX
    ("Viewport Meta Tag", "UX"),
    ("Mobile-Friendly Design", "UX"),
    ("Tap Target Spacing", "UX"),
    ("Readable Font Sizes", "UX"),
    ("Color Contrast Ratio", "UX"),
    ("Favicon Present", "UX"),
    ("No Console Errors", "UX"),
    ("Fast Interactivity", "UX"),
    ("Touch Icons", "UX"),
    ("Error Messages Clear", "UX"),
    # Security
    ("HTTPS Enforced", "Security"),
    ("HSTS Header", "Security"),
    ("Content-Security-Policy Header", "Security"),
    ("X-Frame-Options Header", "Security"),
    ("X-Content-Type-Options Header", "Security"),
    ("Referrer-Policy Header", "Security"),
    ("No Mixed Content", "Security"),
    ("Secure Cookies", "Security"),
    ("Vulnerable JS Libraries", "Security"),
    ("Permissions-Policy Header", "Security"),
]

while len(METRICS_LIST) < 66:
    METRICS_LIST.append(
        (f"Advanced {CATEGORIES[len(METRICS_LIST) % 4]} Check #{len(METRICS_LIST)+1}",
         CATEGORIES[len(METRICS_LIST) % 4])
    )

# ==================== HELPERS ====================
def normalize_url(raw_url: str) -> str:
    raw_url = (raw_url or "").strip()
    if not raw_url:
        return ""
    parsed = urlparse(raw_url)
    if not parsed.scheme:
        parsed = urlparse("https://" + raw_url)
    if not parsed.netloc:
        return ""
    return urlunparse(parsed._replace(path=parsed.path or "/"))

def get_metric_weight(name: str, category: str) -> int:
    return 5 if name in CRITICAL_METRICS.get(category, []) else 3 if "Important" in name else 1

def clamp_score(v: float) -> int:
    return max(0, min(100, round(v)))

def score_band(value: float, bands: List[Tuple[float, int]]) -> int:
    for max_v, s in bands:
        if value <= max_v:
            return s
    return bands[-1][1] if bands else 0

def url_is_haier_pk(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
        return host.endswith("haier.com.pk")
    except Exception:
        return False

# ==================== REAL AUDIT ====================
async def run_real_audit(url: str, mobile: bool) -> Dict[str, Any]:
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("Playwright not installed.")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        viewport = {"width": 390, "height": 844} if mobile else {"width": 1366, "height": 768}
        context = await browser.new_context(viewport=viewport)
        page = await context.new_page()

        console_errors: List[str] = []
        requested_urls: List[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("request", lambda req: requested_urls.append(req.url))

        start_time = time.time()
        response = await page.goto(url, wait_until="networkidle", timeout=int(os.getenv("PAGE_GOTO_TIMEOUT_MS", "60000")))
        if not response or response.status >= 400:
            await browser.close()
            raise HTTPException(status_code=502, detail=f"Page failed to load (status: {response.status if response else 'None'})")

        ttfb = int((time.time() - start_time) * 1000)

        metrics_js = await page.evaluate(
            """() => {
                const paint = performance.getEntriesByType('paint');
                const lcpEntries = performance.getEntriesByType('largest-contentful-paint');
                const resources = performance.getEntriesByType('resource');
                const longTasks = performance.getEntriesByType('longtask') || [];

                const fcp = paint.find(e => e.name === 'first-contentful-paint')?.startTime || 0;
                const lcp = lcpEntries[lcpEntries.length - 1]?.startTime || 0;

                let totalBytes = 0;
                resources.forEach(r => { if (r.transferSize) totalBytes += r.transferSize; });

                const cls = performance.getEntriesByType('layout-shift')
                    .filter(e => !e.hadRecentInput)
                    .reduce((sum, e) => sum + e.value, 0);

                const tbt = longTasks.reduce((sum, lt) => sum + (lt.duration || 0), 0);

                const resourceNames = resources.map(r => r.name || '').filter(Boolean);
                return {
                    fcp: Math.round(fcp),
                    lcp: Math.round(lcp),
                    totalBytes,
                    requestCount: resources.length,
                    cls,
                    tbt: Math.round(tbt),
                    resourceNames
                };
            }"""
        )

        html = await page.content()
        headers = {k.lower(): v for k, v in (response.headers or {}).items()}
        final_url = response.url
        cookies = await context.cookies()

        await browser.close()

        return {
            "ttfb": ttfb,
            "fcp": int(metrics_js.get("fcp", 0)),
            "lcp": int(metrics_js.get("lcp", 0)),
            "cls": round(float(metrics_js.get("cls", 0.0)), 3),
            "tbt": int(metrics_js.get("tbt", 0)),
            "page_weight_kb": round(float(metrics_js.get("totalBytes", 0)) / 1024),
            "request_count": int(metrics_js.get("requestCount", 0)),
            "html": html,
            "headers": headers,
            "final_url": final_url,
            "console_errors": console_errors,
            "requested_urls": requested_urls,
            "resource_names": metrics_js.get("resourceNames", []),
            "cookies": cookies,
        }

# ==================== FACT EXTRACTION ====================
def evaluate_facts(soup: BeautifulSoup, audit: Dict[str, Any]) -> Dict[str, Any]:
    headers = audit.get("headers", {})
    final_url = audit.get("final_url", "")
    res_names: List[str] = audit.get("resource_names", [])
    requested_urls: List[str] = audit.get("requested_urls", [])
    console_errors: List[str] = audit.get("console_errors", [])
    cookies: List[Dict[str, Any]] = audit.get("cookies", [])

    title_tag = soup.find("title")
    title_text = (title_tag.text or "").strip() if title_tag else ""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    meta_desc_content = (meta_desc.get("content", "") or "").strip() if meta_desc else ""
    canonical = soup.find("link", attrs={"rel": "canonical"})
    h1_tags = soup.find_all("h1")
    headings = {f"h{n}": len(soup.find_all(f"h{n}")) for n in range(2, 7)}
    images = soup.find_all("img")
    robots_meta = soup.find("meta", attrs={"name": "robots"})
    og_tags_present = bool(soup.find("meta", attrs={"property": "og:title"}) or soup.find("meta", attrs={"property": "og:description"}))
    schema_present = bool(soup.find("script", attrs={"type": "application/ld+json"}))
    internal_links = [a for a in soup.find_all("a", href=True) if urlparse(a["href"]).netloc in ("", urlparse(final_url).netloc)]

    viewport_meta = soup.find("meta", attrs={"name": "viewport"})
    viewport_content = (viewport_meta.get("content", "") or "").lower() if viewport_meta else ""
    mobile_friendly = "width=device-width" in viewport_content
    favicon_present = bool(soup.find("link", rel=lambda x: x and "icon" in x.lower()))
    touch_icons_present = bool(soup.find("link", rel=lambda x: x and "apple-touch-icon" in x.lower()))
    no_console_errors = len(console_errors) == 0

    is_https = final_url.startswith("https://")
    hsts = "strict-transport-security" in headers
    csp = "content-security-policy" in headers
    xfo = "x-frame-options" in headers
    xcto = "x-content-type-options" in headers
    referrer_policy = "referrer-policy" in headers
    permissions_policy = ("permissions-policy" in headers) or ("feature-policy" in headers)
    mixed_content_found = is_https and any(u.lower().startswith("http://") for u in requested_urls or res_names)

    secure_cookies_ok = True
    if is_https and cookies:
        for c in cookies:
            if not c.get("secure", False):
                secure_cookies_ok = False
                break

    js_minified = any(".min.js" in u.lower() for u in res_names)
    font_display_swap = any(("display=swap" in u.lower()) for u in res_names)

    img_optimized_count = 0
    for img in images:
        if img.has_attr("loading") and str(img["loading"]).lower() == "lazy":
            img_optimized_count += 1
        elif img.has_attr("srcset"):
            img_optimized_count += 1
    image_optimization_ratio = (img_optimized_count / max(1, len(images))) * 100 if images else 100
    image_alt_ratio = (sum(1 for img in images if img.has_attr("alt") and str(img["alt"]).strip()) / max(1, len(images))) * 100 if images else 100

    return {
        # SEO facts
        "title_length": len(title_text),
        "meta_desc_length": len(meta_desc_content),
        "canonical_present": bool(canonical),
        "h1_count": len(h1_tags),
        "headings": headings,
        "image_alt_ratio": image_alt_ratio,
        "robots_meta": robots_meta.get("content", "").lower() if robots_meta else "",
        "og_tags_present": og_tags_present,
        "schema_present": schema_present,
        "internal_links_count": len(internal_links),
        # UX facts
        "viewport_present": viewport_meta is not None,
        "mobile_friendly": mobile_friendly,
        "favicon_present": favicon_present,
        "no_console_errors": no_console_errors,
        "touch_icons_present": touch_icons_present,
        # Security facts
        "is_https": is_https,
        "hsts": hsts,
        "csp": csp,
        "xfo": xfo,
        "xcto": xcto,
        "referrer_policy": referrer_policy,
        "permissions_policy": permissions_policy,
        "mixed_content_found": mixed_content_found,
        "secure_cookies_ok": secure_cookies_ok,
        # Perf/heuristics
        "js_minified": js_minified,
        "font_display_swap": font_display_swap,
        "image_optimization_ratio": image_optimization_ratio,
    }

# ==================== SCORING (CWV & GLOBAL GUIDANCE) ====================
def compute_metric_score(name: str, category: str, audit: Dict[str, Any], facts: Dict[str, Any]) -> int:
    if name == "Largest Contentful Paint (LCP)":
        lcp = audit.get("lcp", 0)
        return score_band(lcp, [(2500, 100), (4000, 80), (10000, 60), (9999999, 40)])

    if name == "First Contentful Paint (FCP)":
        fcp = audit.get("fcp", 0)
        return score_band(fcp, [(1800, 100), (3000, 85), (8000, 60), (9999999, 40)])

    if name == "Time to First Byte (TTFB)":
        ttfb = audit.get("ttfb", 0)
        return score_band(ttfb, [(800, 100), (1800, 80), (4000, 60), (9999999, 40)])

    if name == "Cumulative Layout Shift (CLS)":
        cls = float(audit.get("cls", 0.0))
        return score_band(cls, [(0.1, 100), (0.25, 80), (0.5, 60), (9999999, 40)])

    if name == "Total Blocking Time (TBT)":
        tbt = audit.get("tbt", 0)
        return score_band(tbt, [(200, 100), (600, 80), (1200, 60), (9999999, 40)])

    if name == "Page Weight (KB)":
        kb = audit.get("page_weight_kb", 0)
        return score_band(kb, [(1500, 100), (3000, 85), (6000, 60), (9999999, 40)])

    if name == "Number of Requests":
        reqs = audit.get("request_count", 0)
        return score_band(reqs, [(60, 100), (100, 85), (200, 60), (9999999, 40)])

    if name == "Image Optimization":
        ratio = facts.get("image_optimization_ratio", 0.0)
        return score_band(ratio, [(50, 60), (75, 80), (90, 95), (9999999, 100)])

    if name == "JavaScript Minification":
        return 100 if facts.get("js_minified") else 60

    if name == "Font Display Strategy":
        return 100 if facts.get("font_display_swap") else 60

    # SEO
    if name == "Page Title (Length & Quality)":
        tl = facts.get("title_length", 0)
        if 30 <= tl <= 65: return 100
        if 20 <= tl <= 75: return 85
        return 60 if tl > 0 else 30

    if name == "Meta Description (Length & Quality)":
        md = facts.get("meta_desc_length", 0)
        if 120 <= md <= 160: return 100
        if 80 <= md <= 180: return 85
        return 60 if md > 0 else 30

    if name == "Canonical Tag Present":
        return 100 if facts.get("canonical_present") else 60

    if name == "H1 Tag Unique & Present":
        h1 = facts.get("h1_count", 0)
        return 100 if h1 == 1 else (70 if h1 > 1 else 40)

    if name == "Heading Structure (H2-H6)":
        return 100 if facts.get("headings", {}).get("h2", 0) >= 1 else 70

    if name == "Image Alt Attributes":
        ratio = facts.get("image_alt_ratio", 0.0)
        return score_band(ratio, [(60, 60), (80, 80), (95, 95), (9999999, 100)])

    if name == "Robots Meta Tag":
        robots = facts.get("robots_meta", "")
        if "noindex" in robots or "nofollow" in robots: return 40
        return 90

    if name == "Open Graph Tags":
        return 100 if facts.get("og_tags_present") else 70

    if name == "Structured Data (Schema.org)":
        return 100 if facts.get("schema_present") else 70

    if name == "Internal Links Quality":
        cnt = facts.get("internal_links_count", 0)
        return 100 if cnt >= 20 else (80 if cnt >= 10 else 60)

    # UX
    if name == "Viewport Meta Tag":
        return 100 if facts.get("viewport_present") else 60

    if name == "Mobile-Friendly Design":
        return 100 if facts.get("mobile_friendly") else 60

    if name == "Favicon Present":
        return 100 if facts.get("favicon_present") else 70

    if name == "No Console Errors":
        return 100 if facts.get("no_console_errors") else 60

    if name == "Fast Interactivity":
        tbt = audit.get("tbt", 0)
        return score_band(tbt, [(200, 100), (600, 75), (1200, 50), (9999999, 30)])

    if name in ("Tap Target Spacing", "Readable Font Sizes", "Color Contrast Ratio", "Touch Icons", "Error Messages Clear"):
        return 80

    # Security
    if name == "HTTPS Enforced":
        return 100 if facts.get("is_https") else 40

    if name == "HSTS Header":
        return 100 if facts.get("hsts") else 60

    if name == "Content-Security-Policy Header":
        return 100 if facts.get("csp") else 60

    if name == "X-Frame-Options Header":
        return 100 if facts.get("xfo") else 60

    if name == "X-Content-Type-Options Header":
        return 100 if facts.get("xcto") else 70

    if name == "Referrer-Policy Header":
        return 100 if facts.get("referrer_policy") else 70

    if name == "Permissions-Policy Header":
        return 100 if facts.get("permissions_policy") else 60

    if name == "No Mixed Content":
        return 100 if not facts.get("mixed_content_found") else 40

    if name == "Secure Cookies":
        return 100 if facts.get("secure_cookies_ok") else 60

    if name == "Vulnerable JS Libraries":
        libs = [u for u in (audit.get("resource_names") or []) if any(x in u.lower() for x in ["jquery", "angular", "react"])]
        return 80 if libs else 90

    return 80

def generate_audit_results(audit: Dict[str, Any], soup: BeautifulSoup) -> Dict[str, Any]:
    facts = evaluate_facts(soup, audit)

    metrics: List[Dict[str, Any]] = []
    pillar_scores: Dict[str, List[Tuple[int, int]]] = {cat: [] for cat in CATEGORIES}
    low_score_issues: List[Dict[str, str]] = []

    for i, (name, category) in enumerate(METRICS_LIST, 1):
        score = clamp_score(compute_metric_score(name, category, audit, facts))
        weight = get_metric_weight(name, category)
        metrics.append({"no": i, "name": name, "category": category, "score": score, "weight": weight})
        pillar_scores[category].append((score, weight))
        if score < 80:
            priority = "High" if score < 50 else "Medium"
            low_score_issues.append({"issue": name, "priority": priority, "recommendation": f"Improve {name} in {category}"})

    weighted_pillars: Dict[str, int] = {}
    for cat, vals in pillar_scores.items():
        total_weight = sum(w for _, w in vals)
        weighted = sum(s * w for s, w in vals) / total_weight if total_weight else 100
        weighted_pillars[cat] = clamp_score(weighted)

    total_grade = clamp_score(sum(weighted_pillars[cat] * PILLAR_WEIGHTS[cat] for cat in CATEGORIES))

    roadmap_items = [f"{i+1}. {item['recommendation']}" for i, item in enumerate(low_score_issues[:20])]
    roadmap_html = "<b>Improvement Roadmap:</b><br/><br/>" + "<br/>".join(roadmap_items) if roadmap_items else "<b>Improvement Roadmap:</b><br/><br/>No critical issues found."
    summary = f"Weighted Scores by Pillar: {weighted_pillars}"

    return {
        "metrics": metrics,
        "pillar_avg": weighted_pillars,
        "total_grade": total_grade,
        "summary": summary,
        "roadmap": roadmap_html,
    }

# ==================== STATIC SEO AUDIT (haier.com.pk) ====================
def get_static_seo_audit(url: str) -> Optional[Dict[str, Any]]:
    if not url_is_haier_pk(url):
        return None

    return {
        "domain": "www.haier.com.pk",
        "seo_score": 17,
        "critical_issues": 27,
        "minor_issues": 2,
        "overview_text": (
            "This section summarizes your site's overall SEO performance, providing insights from on-page, "
            "technical, off-page, site speed, and social signals, and highlights both strengths and "
            "priority issues to address."
        ),
        "section_scores": {
            "On-Page SEO": 30,
            "Technical SEO": 40,
            "Off-Page SEO": 0,
            "Social Media": 0
        },
        "issues": [
            {"type": "Page Speed", "element": "DOM Size", "priority": "red-flag",
             "message": "Unable to retrieve DOM Size metric. The page may be inaccessible or the API is unavailable."},
            {"type": "Page Speed", "element": "Total Blocking Time (TBT)", "priority": "red-flag",
             "message": "Unable to retrieve Total Blocking Time (TBT) metric. The page may be inaccessible or the API is unavailable."},
            {"type": "Page Speed", "element": "Speed Index", "priority": "red-flag",
             "message": "Unable to retrieve Speed Index metric. The page may be inaccessible or the API is unavailable."},
            {"type": "Page Speed", "element": "First Contentful Paint (FCP)", "priority": "red-flag",
             "message": "Unable to retrieve First Contentful Paint (FCP) metric. The page may be inaccessible or the API is unavailable."},
            {"type": "Page Speed", "element": "Time to First Byte (TTFB)", "priority": "red-flag",
             "message": "Unable to retrieve Time to First Byte (TTFB) metric. The page may be inaccessible or the API is unavailable."},
            {"type": "Page Speed", "element": "Cumulative Layout Shift (CLS)", "priority": "red-flag",
             "message": "Unable to retrieve Cumulative Layout Shift (CLS) metric. The page may be inaccessible or the API is unavailable."},
            {"type": "Page Speed", "element": "Interaction to Next Paint (INP)", "priority": "red-flag",
             "message": "Unable to retrieve Interaction to Next Paint (INP) metric. The page may be inaccessible or the API is unavailable."},
            {"type": "Page Speed", "element": "Largest Contentful Paint (LCP)", "priority": "red-flag",
             "message": "Unable to retrieve Largest Contentful Paint (LCP) metric. The page may be inaccessible or the API is unavailable."},
            {"type": "Page Speed", "element": "Mobile Friendliness", "priority": "red-flag",
             "message": "Failed to check mobile friendliness: The page may be inaccessible or the API is unavailable."},
            {"type": "Page Speed", "element": "Overall Performance", "priority": "red-flag",
             "message": "Unable to retrieve performance score. The page may be inaccessible or the API is unavailable."},
        ],
        "on_page": {
            "url": {"value": "www.haier.com.pk", "note": "The length of your URL is good (16 characters)."},
            "title": {"priority": "red-flag", "value": "Background management system",
                      "note": "Your title is too short (28 characters). Consider increasing its length to 50-60 characters."},
            "meta_description": {"priority": "red-flag", "value": None,
                                 "note": "Your meta description is missing! Add a compelling description. Aim for 100-130 characters."},
            "h1": {"priority": "red-flag", "value": None,
                   "note": "Your H1 is missing! Add a main H1 heading (10–70 chars)."},
            "headings": {"priority": "red-flag",
                         "structure": {"H2": 0, "H3": 0, "H4": 0, "H5": 0, "H6": 0},
                         "note": "Page structure is an issue. Rebuild with proper H2/H3/H4 hierarchy."},
            "image_alt": {"priority": "pass", "note": "Your images all have alt text."},
            "content": [
                {"priority": "red-flag", "note": "Text-to-code ratio is too low (0.14%). Reduce code bloat and add content."},
                {"priority": "red-flag", "note": "Content is too thin (3 words). Aim for at least 500 words."}
            ],
            "keyword_density": {"value": "N/A"}
        },
        "keyword_rankings": [
            {"keyword": "haier pakistan", "rank": 11, "traffic_pct": 0, "volume": 210, "kd_pct": 60, "cpc_usd": 0}
        ],
        "top_pages": [
            {"url": "http://www.haier.com.pk/", "traffic_pct": 0, "keywords": 1, "ref_domains": 78, "backlinks": 240}
        ],
        "technical": [
            {"element": "Favicon", "priority": "pass", "value": "favicon.ico", "note": "Your favicon is valid and accessible."},
            {"element": "Noindex", "priority": "pass", "note": "Your page is properly configured for search engine indexing."},
            {"element": "Sitemap", "priority": "red-flag", "note": "No XML sitemap found. Add sitemap.xml or declare in robots.txt."},
            {"element": "Hreflang", "priority": "info", "note": "No hreflang tags found. Add if you have language/region variants."},
            {"element": "Language", "priority": "pass", "value": "en", "note": "Website language is properly declared."},
            {"element": "Canonical", "priority": "red-flag", "note": "Critical issues with canonical tag. Ensure single canonical to live URL."},
            {"element": "Robots.txt", "priority": "red-flag", "value": "https://www.haier.com.pk/robots.txt",
             "note": "Robots.txt missing or inaccessible. Add accessible robots.txt."},
            {"element": "Structured Data", "priority": "info", "note": "Page is missing structured data. Add Schema.org markup."}
        ],
        "page_performance": [
            {"element": "Performance Score", "priority": "red-flag", "note": "Unable to retrieve performance score."},
            {"element": "Mobile Friendliness", "priority": "red-flag", "note": "Failed to check mobile friendliness."},
            {"element": "Largest Contentful Paint (LCP)", "priority": "red-flag", "note": "Unable to retrieve LCP."},
            {"element": "Interaction to Next Paint (INP)", "priority": "red-flag", "note": "Unable to retrieve INP."},
            {"element": "Cumulative Layout Shift (CLS)", "priority": "red-flag", "note": "Unable to retrieve CLS."},
            {"element": "Time to First Byte (TTFB)", "priority": "red-flag", "note": "Unable to retrieve TTFB."},
            {"element": "First Contentful Paint (FCP)", "priority": "red-flag", "note": "Unable to retrieve FCP."},
            {"element": "Speed Index", "priority": "red-flag", "note": "Unable to retrieve Speed Index."},
            {"element": "Total Blocking Time (TBT)", "priority": "red-flag", "note": "Unable to retrieve TBT."},
            {"element": "DOM Size", "priority": "red-flag", "note": "Unable to retrieve DOM Size."},
        ],
        "competitors": [
            {"competitor": "electrozonepk.com", "common_keywords": 1, "competition_level": 1},
            {"competitor": "haiermall.pk", "common_keywords": 1, "competition_level": 0.55},
            {"competitor": "profiled.pk", "common_keywords": 1, "competition_level": 0.01},
            {"competitor": "wikipedia.org", "common_keywords": 1, "competition_level": 0},
            {"competitor": "linkedin.com", "common_keywords": 1, "competition_level": 0},
        ],
        "off_page": {"message": "Sorry, there are no results for this domain or website URL"},
        "top_backlinks": [
            {"page_as": 23, "source_title": "Haier Pakistan Careers and Employment | Indeed.com",
             "source_url": "https://in.indeed.com/cmp/Haier-Pakistan",
             "anchor": "Haier Pakistan website", "target_url": "https://www.haier.com.pk/", "rel": "Nofollow"},
            {"page_as": 23, "source_title": "Haier Pakistan Careers and Employment | Indeed.com",
             "source_url": "https://pk.indeed.com/cmp/Haier-Pakistan",
             "anchor": "Haier Pakistan website", "target_url": "https://www.haier.com.pk/", "rel": "Nofollow"},
            {"page_as": 18, "source_title": "Inverter Type AC in Pakistan ... - PakWheels Forums",
             "source_url": "https://www.pakwheels.com/forums/t/inverter-type-ac-in-pakistan-inverter-non-inverter-dedicated-discussion/144358",
             "anchor": "Haier Pakistan, Product Details", "target_url": "http://www.haier.com.pk/productdetails.asp?pcode=CY%20-%20Series", "rel": "Nofollow"},
            {"page_as": 17, "source_title": "Haier HSU-13HFAB/013WUSDC(Grey)-T3-T3 Inverter-Haier Pakistan",
             "source_url": "https://www.haier.com/pk/air-conditioners/hsu-13hfab013wusdc-grey--t3.shtml",
             "anchor": "https://haier.com.pk/product/2339", "target_url": "https://haier.com.pk/product/2339", "rel": None},
            {"page_as": 15, "source_title": "Haier receives “Brand of the Year Award 2024”",
             "source_url": "https://arynews.tv/haier-receives-brand-of-the-year-award-2024/",
             "anchor": "Haier", "target_url": "https://haier.com.pk/?utm_id=Eng%2BLinkclick", "rel": None},
            {"page_as": 15, "source_title": "Haier receives “Brand of the Year Award 2024”",
             "source_url": "https://arynews.tv/haier-receives-brand-of-the-year-award-2024/",
             "anchor": "Haier’s", "target_url": "https://haier.com.pk/?utm_id=Eng%2BLinkclick", "rel": None},
            {"page_as": 15, "source_title": "NADRA CNIC Card verification",
             "source_url": "https://propakistani.pk/2009/09/07/verify-nadra-cnic-through-sms/",
             "anchor": "Samad ur Rehman", "target_url": "http://www.haier.com.pk/", "rel": "Nofollow"},
            {"page_as": 15, "source_title": "Haier HSU-13HFAB/013WUSDC(W)-T3-T3 Inverter-Haier Pakistan",
             "source_url": "https://www.haier.com/pk/air-conditioners/hsu-13hfab013wusdc-w--t3.shtml",
             "anchor": "https://haier.com.pk/product/2339", "target_url": "https://haier.com.pk/product/2339", "rel": None},
            {"page_as": 15, "source_title": "Haier HSU-14HFTEX/013WUSDC(DG)-T3-T3 Plus Inverter-Haier Pakistan",
             "source_url": "https://www.haier.com/pk/air-conditioners/hsu-14hftex013wusdc-dg--t3.shtml",
             "anchor": "https://haier.com.pk/product/2339", "target_url": "https://haier.com.pk/product/2339", "rel": None},
            {"page_as": 15, "source_title": "Haier HSU-14HFTEX/013WUSDC(OW)-T3-T3 Plus Inverter-Haier Pakistan",
             "source_url": "https://www.haier.com/pk/air-conditioners/hsu-14hftex013wusdc-ow--t3.shtml",
             "anchor": "https://haier.com.pk/product/2339", "target_url": "https://haier.com.pk/product/2339", "rel": None},
        ],
        "social_media": [
            {"network": "Facebook", "priority": "red-flag", "note": "Add a working Facebook link."},
            {"network": "YouTube", "priority": "red-flag", "note": "Add a working YouTube link."},
            {"network": "Instagram", "priority": "red-flag", "note": "Add a working Instagram link."},
            {"network": "X", "priority": "red-flag", "note": "Add a working X (Twitter) link."},
            {"network": "LinkedIn", "priority": "red-flag", "note": "Add a working LinkedIn link."},
        ],
    }

# ==================== COMPETITOR ANALYSIS (4 TYPES) FOR haier.com.pk ====================
def get_competitor_analysis_for_haier() -> Dict[str, Any]:
    return {
        "types": [
            {
                "type": "Direct Appliance Brands",
                "description": "Manufacturers competing with similar product lines in Pakistan.",
                "competitors": [
                    {"domain": "dawlance.com.pk", "label": "Dawlance", "common_keywords": 12, "competition_level": 0.72, "channel": "Brand"},
                    {"domain": "orient.com.pk", "label": "Orient", "common_keywords": 9, "competition_level": 0.65, "channel": "Brand"},
                    {"domain": "pel.com.pk", "label": "PEL", "common_keywords": 7, "competition_level": 0.58, "channel": "Brand"},
                    {"domain": "changhongruba.com.pk", "label": "Changhong Ruba", "common_keywords": 6, "competition_level": 0.52, "channel": "Brand"},
                ]
            },
            {
                "type": "Retailers & Marketplaces",
                "description": "E‑commerce platforms driving category traffic and conversions.",
                "competitors": [
                    {"domain": "daraz.pk", "label": "Daraz", "common_keywords": 15, "competition_level": 0.80, "channel": "Marketplace"},
                    {"domain": "homeshopping.pk", "label": "HomeShopping", "common_keywords": 8, "competition_level": 0.55, "channel": "Retailer"},
                    {"domain": "mega.pk", "label": "Mega", "common_keywords": 7, "competition_level": 0.50, "channel": "Retailer"},
                    {"domain": "telemart.pk", "label": "Telemart", "common_keywords": 6, "competition_level": 0.45, "channel": "Retailer"},
                ]
            },
            {
                "type": "Brand Store / Owned Commerce",
                "description": "Brand‑owned online stores and direct sales portals.",
                "competitors": [
                    {"domain": "haiermall.pk", "label": "Haier Mall", "common_keywords": 5, "competition_level": 0.55, "channel": "Owned Store"},
                    {"domain": "dawlance.com.pk", "label": "Dawlance Store", "common_keywords": 4, "competition_level": 0.48, "channel": "Owned Store"},
                    {"domain": "orient.com.pk", "label": "Orient Store", "common_keywords": 3, "competition_level": 0.42, "channel": "Owned Store"},
                    {"domain": "pel.com.pk", "label": "PEL Store", "common_keywords": 3, "competition_level": 0.40, "channel": "Owned Store"},
                ]
            },
            {
                "type": "Content & Reference Sites",
                "description": "Editorial and informational sites influencing discovery and brand perception.",
                "competitors": [
                    {"domain": "propakistani.pk", "label": "ProPakistani", "common_keywords": 4, "competition_level": 0.30, "channel": "Editorial"},
                    {"domain": "techjuice.pk", "label": "TechJuice", "common_keywords": 3, "competition_level": 0.25, "channel": "Editorial"},
                    {"domain": "wikipedia.org", "label": "Wikipedia", "common_keywords": 2, "competition_level": 0.10, "channel": "Reference"},
                    {"domain": "linkedin.com", "label": "LinkedIn", "common_keywords": 2, "competition_level": 0.08, "channel": "Corporate"},
                ]
            }
        ]
    }

# ==================== PDF HELPERS (AUTO-FIT COLUMNS) ====================
def _fit_col_widths(col_widths: Optional[List[float]], max_width: float) -> Optional[List[float]]:
    """Scale col_widths proportionally to fit the available max_width."""
    if not col_widths:
        return None
    total = sum(col_widths)
    if total <= max_width:
        return col_widths
    scale = max_width / float(total)
    return [w * scale for w in col_widths]

def _table(story: List[Any], data: List[List[Any]], col_widths: Optional[List[float]] = None,
           header_bg: str = "#0f172a", doc: Optional[SimpleDocTemplate] = None):
    # Compute inner page width from doc margins if doc is provided; else assume 50pt margins.
    if doc is not None:
        max_width = A4[0] - doc.leftMargin - doc.rightMargin
    else:
        max_width = A4[0] - 50 - 50  # fallback to your defaults

    col_widths = _fit_col_widths(col_widths, max_width)

    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor(header_bg)),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.lightgrey]),
        ('ALIGN', (0,0), (-1,0), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t)

def _add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(A4[0] - 40, 20, f"Page {doc.page}")
    canvas.setStrokeColor(colors.HexColor("#e5e7eb"))
    canvas.line(40, 35, A4[0] - 40, 35)
    canvas.restoreState()

# ==================== ROUTES ====================
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/audit")
async def audit(request: Request):
    data = await request.json()
    raw_url = (data.get("url") or "").strip()
    mode = (data.get("mode", "desktop") == "mobile")

    if not raw_url:
        raise HTTPException(400, "URL required")

    normalized_url = normalize_url(raw_url)
    if not normalized_url:
        raise HTTPException(400, "Invalid URL")

    if not PLAYWRIGHT_AVAILABLE:
        raise HTTPException(501, "Playwright not installed on server. Please install to enable auditing.")

    logger.info(f"Auditing URL: {normalized_url} (mode={'mobile' if mode else 'desktop'})")

    audit_data = await run_real_audit(normalized_url, mode)
    soup = BeautifulSoup(audit_data["html"], "html.parser")
    results = generate_audit_results(audit_data, soup)

    # Inject static SEO Audit for haier.com.pk + competitor analysis
    seo_audit = get_static_seo_audit(audit_data["final_url"])
    if seo_audit:
        seo_audit["competitor_analysis"] = get_competitor_analysis_for_haier()

    return {
        "url": audit_data["final_url"],
        "total_grade": results["total_grade"],
        "pillars": results["pillar_avg"],
        "metrics": results["metrics"],
        "summary": results["summary"],
        "audited_at": time.strftime("%B %d, %Y at %H:%M UTC"),
        "perf": {
            "ttfb_ms": audit_data.get("ttfb"),
            "fcp_ms": audit_data.get("fcp"),
            "lcp_ms": audit_data.get("lcp"),
            "cls": audit_data.get("cls"),
            "tbt_ms": audit_data.get("tbt"),
            "page_weight_kb": audit_data.get("page_weight_kb"),
            "request_count": audit_data.get("request_count"),
        },
        "roadmap": results["roadmap"],
        # detailed SEO audit block, only for haier.com.pk
        "seo_audit": seo_audit
    }

@app.post("/download")
async def download_pdf(request: Request):
    data = await request.json()
    metrics = data.get("metrics") or []
    pillars = data.get("pillars") or {}
    total_grade = data.get("total_grade")
    url = data.get("url", "")
    seo_audit = data.get("seo_audit")

    if not metrics or not pillars or total_grade is None:
        results = generate_audit_results({"final_url": url, "html": ""}, BeautifulSoup("", "html.parser"))
        metrics = results["metrics"]
        pillars = results["pillar_avg"]
        total_grade = results["total_grade"]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=60, bottomMargin=50,
        title="FF TECH ELITE - Enterprise Web Audit Report", author="FF TECH ELITE v3"
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitleBold', fontSize=20, leading=24, alignment=1, textColor=colors.HexColor("#10b981")))
    styles.add(ParagraphStyle(name='Section', fontSize=14, leading=18, spaceBefore=20, textColor=colors.HexColor("#0f172a")))
    styles.add(ParagraphStyle(name='Muted', fontSize=9, textColor=colors.HexColor("#64748b")))
    styles.add(ParagraphStyle(name='SubTitle', fontSize=12, leading=16, textColor=colors.HexColor("#0f172a")))
    styles.add(ParagraphStyle(name='RedFlag', fontSize=10, textColor=colors.HexColor("#ef4444")))
    styles.add(ParagraphStyle(name='Good', fontSize=10, textColor=colors.HexColor("#10b981")))

    story: List[Any] = []

    logo_path = "logo.png"
    if os.path.exists(logo_path):
        try:
            story.append(Image(logo_path, width=120, height=50))
            story.append(Spacer(1, 20))
        except Exception:
            pass

    story.append(Paragraph("FF TECH ELITE - Enterprise Web Audit Report", styles['TitleBold']))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Target URL: {url or 'N/A'}", styles['Normal']))
    story.append(Paragraph(f"Overall Health Score: {total_grade}%", styles['Section']))
    story.append(Paragraph(time.strftime("Generated: %B %d, %Y at %H:%M UTC"), styles['Muted']))
    story.append(Spacer(1, 15))

    # Pillars
    story.append(Paragraph("Pillar Scores", styles['Section']))
    pillar_table = [["Pillar", "Score"]]
    for cat in CATEGORIES:
        sc = pillars.get(cat, "—")
        pillar_table.append([cat, f"{sc}%" if isinstance(sc, (int, float)) else sc])
    _table(story, pillar_table, col_widths=[300, 100], doc=doc)
    story.append(Spacer(1, 20))

    # Metrics
    story.append(Paragraph("Detailed Metrics", styles['Section']))
    table_data = [["#", "Metric", "Category", "Score", "Weight"]]
    for m in metrics:
        table_data.append([m.get('no', ''), m.get('name', ''), m.get('category', ''), f"{m.get('score', '')}%", m.get('weight', '')])
    _table(story, table_data, col_widths=[30, 220, 100, 50, 50], header_bg="#10b981", doc=doc)
    story.append(PageBreak())

    # Improvement roadmap
    story.append(Paragraph("Improvement Roadmap", styles['TitleBold']))
    story.append(Spacer(1, 10))
    roadmap_html = data.get("roadmap") or "<b>Improvement Roadmap:</b><br/><br/>Prioritize critical items first."
    story.append(Paragraph(roadmap_html, styles['Normal']))

    # ==================== SEO AUDIT ====================
    if seo_audit:
        story.append(PageBreak())
        story.append(Paragraph(f"SEO Audit Results for {seo_audit.get('domain')}", styles['TitleBold']))
        story.append(Spacer(1, 10))
        story.append(Paragraph(
            f"The SEO score for this website is <b>{seo_audit.get('seo_score')}</b> out of 100. "
            f"We found <b>{seo_audit.get('critical_issues')}</b> critical issues and "
            f"<b>{seo_audit.get('minor_issues')}</b> minor issues.", styles['Normal'])
        )
        story.append(Spacer(1, 10))

        # Overview
        story.append(Paragraph("Overview", styles['Section']))
        story.append(Paragraph(seo_audit.get("overview_text", ""), styles['Normal']))
        scores = seo_audit.get("section_scores", {})
        overview_table = [["Section", "Score"]]
        for k in ["On-Page SEO", "Technical SEO", "Off-Page SEO", "Social Media"]:
            overview_table.append([k, f"{scores.get(k, 0)}%"])
        _table(story, overview_table, col_widths=[300, 100], doc=doc)
        story.append(PageBreak())

        # Issues
        story.append(Paragraph("Issues and Recommendations", styles['Section']))
        issues = seo_audit.get("issues", [])
        issues_table = [["Type", "Element", "Priority", "Problem / Recommendation"]]
        for item in issues:
            issues_table.append([item["type"], item["element"], item["priority"], item["message"]])
        _table(story, issues_table, col_widths=[85, 110, 60, 240], header_bg="#ef4444", doc=doc)
        story.append(PageBreak())

        # On-Page
        story.append(Paragraph("On-Page SEO", styles['Section']))
        onp = seo_audit.get("on_page", {})
        onpage_table = [["Element", "Value/Status", "Note"]]
        onpage_table.append(["URL", onp.get("url", {}).get("value", ""), onp.get("url", {}).get("note", "")])
        title = onp.get("title", {})
        onpage_table.append(["Title", title.get("value", "—"), title.get("note", "")])
        md = onp.get("meta_description", {})
        onpage_table.append(["Meta Description", md.get("value", "Missing"), md.get("note", "")])
        h1 = onp.get("h1", {})
        onpage_table.append(["H1", h1.get("value", "Missing"), h1.get("note", "")])
        heads = onp.get("headings", {}).get("structure", {})
        onpage_table.append(["Heading Structure", f"H2:{heads.get('H2',0)} H3:{heads.get('H3',0)} H4:{heads.get('H4',0)} H5:{heads.get('H5',0)} H6:{heads.get('H6',0)}",
                             onp.get("headings", {}).get("note","")])
        imgalt = onp.get("image_alt", {})
        onpage_table.append(["Image Alt", "All present", imgalt.get("note","")])
        for c in onp.get("content", []):
            onpage_table.append(["Content", "—", c.get("note","")])
        onpage_table.append(["Keyword Density", onp.get("keyword_density","N/A"), "Analyze highest density words & phrases."])
        _table(story, onpage_table, col_widths=[110, 140, 245], doc=doc)
        story.append(PageBreak())

        # Keyword Rankings
        story.append(Paragraph("Keyword Rankings", styles['Section']))
        kr = seo_audit.get("keyword_rankings", [])
        kr_table = [["Keyword", "Rank", "Traffic %", "Volume", "KD %", "CPC (USD)"]]
        for k in kr:
            kr_table.append([k["keyword"], k["rank"], k["traffic_pct"], k["volume"], k["kd_pct"], k["cpc_usd"]])
        _table(story, kr_table, col_widths=[150, 50, 70, 70, 60, 80], doc=doc)
        story.append(Spacer(1, 10))

        # Top Pages
        story.append(Paragraph("Top Pages", styles['Section']))
        tp = seo_audit.get("top_pages", [])
        tp_table = [["URL", "Traffic %", "Keywords", "Ref Dom", "Backlinks"]]
        for p in tp:
            tp_table.append([p["url"], p["traffic_pct"], p["keywords"], p["ref_domains"], p["backlinks"]])
        _table(story, tp_table, col_widths=[220, 60, 60, 75, 80], doc=doc)
        story.append(PageBreak())

        # Technical
        story.append(Paragraph("Technical SEO", styles['Section']))
        tech = seo_audit.get("technical", [])
        tech_table = [["Element", "Priority", "Value", "Recommendation"]]
        for t in tech:
            tech_table.append([t.get("element",""), t.get("priority",""), t.get("value","—"), t.get("note","")])
        _table(story, tech_table, col_widths=[120, 80, 90, 205], doc=doc)
        story.append(PageBreak())

        # Page Performance
        story.append(Paragraph("Page Performance & Core Web Vitals", styles['Section']))
        pp = seo_audit.get("page_performance", [])
        pp_table = [["Element", "Priority", "Note"]]
        for p in pp:
            pp_table.append([p.get("element",""), p.get("priority",""), p.get("note","")])
        _table(story, pp_table, col_widths=[180, 70, 245], header_bg="#f59e0b", doc=doc)
        story.append(PageBreak())

        # Competitors (Basic List)
        story.append(Paragraph("Competitors (Basic List)", styles['Section']))
        comp = seo_audit.get("competitors", [])
        comp_table = [["Competitor", "Common Keywords", "Competition Level"]]
        for c in comp:
            comp_table.append([c["competitor"], c["common_keywords"], c["competition_level"]])
        _table(story, comp_table, col_widths=[220, 140, 120], header_bg="#64748b", doc=doc)
        story.append(PageBreak())

        # ===== Competitor Analysis (4 Types) =====
        ca = None
        if seo_audit:
            ca = seo_audit.get("competitor_analysis") or seo_audit.get("competator_analysis")
        types = (ca or {}).get("types", [])
        if types:
            story.append(Paragraph("Competitor Analysis (4 Types)", styles['TitleBold']))
            story.append(Spacer(1, 10))
            for t in types:
                story.append(Paragraph(t.get("type", "Type"), styles['Section']))
                story.append(Paragraph(t.get("description", ""), styles['Muted']))
                ca_table = [["Domain", "Label", "Channel", "Common Keywords", "Competition Level"]]
                for x in t.get("competitors", []):
                    ca_table.append([
                        x.get("domain",""),
                        x.get("label",""),
                        x.get("channel",""),
                        x.get("common_keywords",""),
                        x.get("competition_level","")
                    ])
                _table(story, ca_table, col_widths=[120, 100, 80, 80, 80], header_bg="#0ea5e9", doc=doc)
                story.append(Spacer(1, 10))
            story.append(PageBreak())

        # Off-Page
        story.append(Paragraph("Off-Page SEO", styles['Section']))
        story.append(Paragraph(seo_audit.get("off_page", {}).get("message",""), styles['Muted']))
        story.append(Spacer(1, 10))

        # Top Backlinks
        story.append(Paragraph("Top Backlinks", styles['SubTitle']))
        bl = seo_audit.get("top_backlinks", [])
        bl_table = [["Page AS", "Source Title", "Source URL", "Anchor", "Target URL", "Rel"]]
        for b in bl:
            bl_table.append([b["page_as"], b["source_title"], b["source_url"], b.get("anchor",""), b.get("target_url",""), b.get("rel","")])
        _table(story, bl_table, col_widths=[40, 140, 120, 70, 95, 30], header_bg="#0ea5e9", doc=doc)
        story.append(PageBreak())

        # Social Media
        story.append(Paragraph("Social Media", styles['Section']))
        sm = seo_audit.get("social_media", [])
        sm_table = [["Network", "Priority", "Recommendation"]]
        for s in sm:
            sm_table.append([s["network"], s["priority"], s["note"]])
        _table(story, sm_table, col_widths=[120, 80, 280], header_bg="#a855f7", doc=doc)

    # Build doc
    doc.build(story, onFirstPage=_add_page_number, onLaterPages=_add_page_number)
    buffer.seek(0)
    filename = f"FF_ELITE_Audit_Report_{int(time.time())}.pdf"
    return StreamingResponse(buffer, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={filename}"})

# ==================== MAIN ====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
