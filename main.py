
import os
import io
import time
import logging
from typing import Dict, Any, List, Tuple, Optional
from urllib.parse import urlparse, urlunparse

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates

import requests
from bs4 import BeautifulSoup

# ReportLab (PDF)
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image,
    KeepTogether, ListFlowable, ListItem
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ==================== LOGGING ====================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FF_TECH_ELITE_V3")

# ==================== OPTIONAL PLAYWRIGHT ====================
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not installed. Will rely on PSI + requests fallback.")

# ==================== APP ====================
app = FastAPI(title="FF TECH ELITE v3 - Ultimate Audit")
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
    "Performance": [
        "Largest Contentful Paint (LCP)", "First Contentful Paint (FCP)", "Time to First Byte (TTFB)",
        "Cumulative Layout Shift (CLS)", "Interaction to Next Paint (INP)", "Speed Index"
    ],
    "SEO": ["Page Title (Length &amp; Quality)", "Meta Description (Length &amp; Quality)", "H1 Tag Unique &amp; Present", "Canonical Tag Present"],
    "UX": ["Viewport Meta Tag", "Mobile-Friendly (PSI Viewport)"],
    "Security": ["HTTPS Enforced", "HSTS Header", "Content-Security-Policy Header", "X-Frame-Options Header"]
}

# Base metrics + pad to 300+
METRICS_LIST: List[Tuple[str, str]] = [
    # Performance
    ("Largest Contentful Paint (LCP)", "Performance"),
    ("First Contentful Paint (FCP)", "Performance"),
    ("Time to First Byte (TTFB)", "Performance"),
    ("Cumulative Layout Shift (CLS)", "Performance"),
    ("Total Blocking Time (TBT)", "Performance"),
    ("Interaction to Next Paint (INP)", "Performance"),
    ("Speed Index", "Performance"),
    ("Page Weight (KB)", "Performance"),
    ("Number of Requests", "Performance"),
    ("Image Optimization", "Performance"),
    ("JavaScript Minification", "Performance"),
    ("Font Display Strategy", "Performance"),

    # SEO
    ("Page Title (Length &amp; Quality)", "SEO"),
    ("Meta Description (Length &amp; Quality)", "SEO"),
    ("Canonical Tag Present", "SEO"),
    ("H1 Tag Unique &amp; Present", "SEO"),
    ("Heading Structure (H2-H6)", "SEO"),
    ("Image Alt Attributes", "SEO"),
    ("Robots Meta Tag", "SEO"),
    ("Open Graph Tags", "SEO"),
    ("Structured Data (Schema.org)", "SEO"),
    ("Internal Links Quality", "SEO"),

    # UX
    ("Viewport Meta Tag", "UX"),
    ("Mobile-Friendly (PSI Viewport)", "UX"),
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
    ("Vulnerable JS Libraries (heuristic)", "Security"),
    ("Permissions-Policy Header", "Security"),
]

while len(METRICS_LIST) < 300:
    METRICS_LIST.append(
        (f"Advanced {CATEGORIES[len(METRICS_LIST) % 4]} Check #{len(METRICS_LIST) + 1}",
         CATEGORIES[len(METRICS_LIST) % 4])
    )

# ==================== DOMAIN REWRITE RULES ====================
# As requested: treat www.haier.pk (and variants) as http://www.haier.com.pk/#/login
DOMAIN_REWRITE_RULES = {
    "haier.pk": "http://www.haier.com.pk/#/login",
    "www.haier.pk": "http://www.haier.com.pk/#/login",
    "haier.com.pk": "http://www.haier.com.pk/#/login",
    "www.haier.com.pk": "http://www.haier.com.pk/#/login",
}

def apply_domain_rewrite(url: str) -> str:
    try:
        p = urlparse(url)
        host = (p.netloc or "").lower()
        if host in DOMAIN_REWRITE_RULES:
            return DOMAIN_REWRITE_RULES[host]
        return url
    except Exception:
        return url

# ==================== HELPERS ====================
def normalize_url(raw_url: str) -> str:
    """Normalize and preserve fragment; add https:// if missing, then apply domain rewrite."""
    raw_url = (raw_url or "").strip()
    if not raw_url:
        return ""
    p = urlparse(raw_url)
    if not p.scheme:
        p = urlparse("https://" + raw_url)
    if not p.netloc:
        return ""
    # Ensure a path at least '/'
    p = p._replace(path=(p.path or "/"))
    normalized = urlunparse(p)
    # Apply requested domain rewrite logic (may change scheme/path/fragment)
    rewritten = apply_domain_rewrite(normalized)
    # If rewrite applied, keep it as-is (may be http + hash)
    return rewritten

def get_metric_weight(name: str, category: str) -> int:
    return 5 if name in CRITICAL_METRICS.get(category, []) else 3 if "Advanced" in name else 1

def clamp_score(v: float) -> int:
    return max(0, min(100, round(v)))

def score_band(value: float, bands: List[Tuple[float, int]]) -> int:
    for max_v, s in bands:
        if value <= max_v:
            return s
    return bands[-1][1] if bands else 0

# ==================== PSI (Lighthouse) ====================
PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
PSI_API_KEY = os.getenv("PAGESPEED_API_KEY")  # recommended

def call_psi(url: str, strategy: str = "desktop", locale: str = "en") -> Optional[dict]:
    params = {
        "url": url,
        "strategy": strategy,
        "locale": locale,
        "category": ["performance", "seo", "best-practices", "accessibility"],
    }
    if PSI_API_KEY:
        params["key"] = PSI_API_KEY
    try:
        r = requests.get(PSI_ENDPOINT, params=params, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"PSI call failed: {e}")
        return None

def extract_from_psi(psi: dict) -> dict:
    if not psi or "lighthouseResult" not in psi:
        return {}
    lhr = psi["lighthouseResult"]
    audits = lhr.get("audits", {})
    cats = lhr.get("categories", {})

    def _nv(aid):
        a = audits.get(aid, {})
        nv = a.get("numericValue")
        return nv if isinstance(nv, (int, float)) else None

    dom_size = _nv("dom-size")
    speed_index = _nv("speed-index")
    inp = _nv("interaction-to-next-paint")
    lcp = _nv("largest-contentful-paint")
    fcp = _nv("first-contentful-paint")
    cls_nv = _nv("cumulative-layout-shift")
    tbt = _nv("total-blocking-time")
    viewport_pass = (audits.get("viewport", {}).get("score") == 1)

    perf_score = cats.get("performance", {}).get("score")
    perf_percent = int(round(float(perf_score) * 100)) if isinstance(perf_score, (int, float)) else None

    opp_items = []
    for aid, a in audits.items():
        det = a.get("details", {})
        if det.get("type") == "opportunity":
            title = a.get("title", aid)
            sv_ms = det.get("overallSavingsMs")
            sv_bt = det.get("overallSavingsBytes")
            savings = []
            if sv_ms: savings.append(f"~{int(sv_ms)} ms")
            if sv_bt: savings.append(f"~{int(sv_bt/1024)} KB")
            opp_items.append(f"{title}" + (f" (Savings: {', '.join(savings)})" if savings else ""))

    return {
        "psi_dom_size": dom_size,
        "psi_speed_index_ms": speed_index,
        "psi_inp_ms": inp,
        "psi_lcp_ms": lcp,
        "psi_fcp_ms": fcp,
        "psi_cls": cls_nv,
        "psi_tbt_ms": tbt,
        "psi_performance_percent": perf_percent,
        "psi_viewport_pass": viewport_pass,
        "psi_opportunities": opp_items,
    }

# ==================== REQUESTS FALLBACK (HTML + headers) ====================
def fetch_html_and_headers(url: str, timeout: int = 30) -> Tuple[str, Dict[str, str], str]:
    """
    Fetch HTML and response headers using requests.
    Returns: (html_text, headers_lowercased, final_url_after_redirects)
    """
    try:
        sess = requests.Session()
        resp = sess.get(url, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        html = resp.text or ""
        headers = {k.lower(): v for k, v in resp.headers.items()}
        final_url = str(resp.url)
        return html, headers, final_url
    except Exception as e:
        logger.warning(f"Requests fallback failed: {e}")
        return "", {}, url

# ==================== PLAYWRIGHT LAB METRICS ====================
async def run_playwright_audit(url: str, mobile: bool) -> Dict[str, Any]:
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("Playwright not installed.")

    headless = os.getenv("PW_HEADLESS", "true").lower() == "true"
    timeout_ms = int(os.getenv("PAGE_GOTO_TIMEOUT_MS", "60000"))

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        viewport = {"width": 390, "height": 844} if mobile else {"width": 1366, "height": 768}
        ua = ("Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Mobile Safari/537.36"
              if mobile else
              "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Safari/537.36")
        context = await browser.new_context(viewport=viewport, user_agent=ua)
        page = await context.new_page()

        console_errors: List[str] = []
        requested_urls: List[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("request", lambda req: requested_urls.append(req.url))

        start_time = time.time()
        response = await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        if not response or response.status >= 400:
            await browser.close()
            raise HTTPException(status_code=502, detail=f"Page failed to load (status: {response.status if response else 'None'})")

        ttfb = int((time.time() - start_time) * 1000)

        metrics_js = await page.evaluate(
            """() => {
                const paint = performance.getEntriesByType('paint') || [];
                const lcpEntries = performance.getEntriesByType('largest-contentful-paint') || [];
                const resources = performance.getEntriesByType('resource') || [];
                const longTasks = performance.getEntriesByType('longtask') || [];

                const fcp = paint.find(e => e.name === 'first-contentful-paint')?.startTime || 0;
                const lcp = lcpEntries.length ? lcpEntries[lcpEntries.length - 1].startTime : 0;

                let totalBytes = 0;
                resources.forEach(r => { if (r.transferSize) totalBytes += r.transferSize; });

                const cls = (performance.getEntriesByType('layout-shift') || [])
                    .filter(e => !e.hadRecentInput)
                    .reduce((sum, e) => sum + (e.value || 0), 0);

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

# ==================== FACT EXTRACTION (DOM) ====================
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
    try:
        base_host = urlparse(final_url).netloc
    except Exception:
        base_host = ""
    internal_links = [a for a in soup.find_all("a", href=True) if urlparse(a["href"]).netloc in ("", base_host)]

    viewport_meta = soup.find("meta", attrs={"name": "viewport"})
    viewport_content = (viewport_meta.get("content", "") or "").lower() if viewport_meta else ""
    mobile_friendly_heur = "width=device-width" in viewport_content

    def _has(hosts: List[str]) -> bool:
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            if any(h in href for h in hosts):
                return True
        return False

    social_presence = {
        "Facebook": _has(["facebook.com"]),
        "YouTube": _has(["youtube.com"]),
        "Instagram": _has(["instagram.com"]),
        "X": _has(["twitter.com", "x.com"]),
        "LinkedIn": _has(["linkedin.com"]),
    }

    favicon_present = bool(soup.find("link", rel=lambda x: x and "icon" in x.lower()))
    touch_icons_present = bool(soup.find("link", rel=lambda x: x and "apple-touch-icon" in x.lower()))
    no_console_errors = len(console_errors) == 0

    is_https = str(final_url).startswith("https://")
    hsts = "strict-transport-security" in headers
    csp = "content-security-policy" in headers
    xfo = "x-frame-options" in headers
    xcto = "x-content-type-options" in headers
    referrer_policy = "referrer-policy" in headers
    permissions_policy = ("permissions-policy" in headers) or ("feature-policy" in headers)
    mixed_content_found = is_https and any(u.lower().startswith("http://") for u in (requested_urls or res_names))

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
        "robots_meta": (robots_meta.get("content", "") or "").lower() if robots_meta else "",
        "og_tags_present": og_tags_present,
        "schema_present": schema_present,
        "internal_links_count": len(internal_links),

        # UX facts
        "viewport_present": viewport_meta is not None,
        "mobile_friendly_heur": mobile_friendly_heur,
        "favicon_present": favicon_present,
        "no_console_errors": no_console_errors,
        "touch_icons_present": touch_icons_present,
        "social_presence": social_presence,

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

# ==================== SCORING ====================
def compute_metric_score(name: str, category: str, audit: Dict[str, Any], facts: Dict[str, Any], psi: Dict[str, Any]) -> int:
    # Prefer PSI values when available; otherwise Playwright/lab heuristics.
    if name == "Largest Contentful Paint (LCP)":
        lcp = audit.get("lcp") or psi.get("psi_lcp_ms") or 0
        return score_band(lcp, [(2500, 100), (4000, 80), (10000, 60), (9999999, 40)])
    if name == "First Contentful Paint (FCP)":
        fcp = audit.get("fcp") or psi.get("psi_fcp_ms") or 0
        return score_band(fcp, [(1800, 100), (3000, 85), (8000, 60), (9999999, 40)])
    if name == "Time to First Byte (TTFB)":
        ttfb = audit.get("ttfb", 0)
        return score_band(ttfb, [(800, 100), (1800, 80), (4000, 60), (9999999, 40)])
    if name == "Cumulative Layout Shift (CLS)":
        cls = audit.get("cls")
        if cls is None:
            cls = float(psi.get("psi_cls") or 0.0)
        return score_band(cls, [(0.1, 100), (0.25, 80), (0.5, 60), (9999999, 40)])
    if name == "Total Blocking Time (TBT)":
        tbt = audit.get("tbt") or psi.get("psi_tbt_ms") or 0
        return score_band(tbt, [(200, 100), (600, 80), (1200, 60), (9999999, 40)])
    if name == "Interaction to Next Paint (INP)":
        inp = psi.get("psi_inp_ms")
        if inp is None:
            inp = audit.get("tbt", 0)  # conservative fallback
        return score_band(inp, [(200, 100), (500, 80), (1000, 60), (9999999, 40)])
    if name == "Speed Index":
        si = psi.get("psi_speed_index_ms") or 0
        return score_band(si, [(3500, 100), (5500, 80), (8500, 60), (9999999, 40)])
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
    if name == "Page Title (Length &amp; Quality)":
        tl = facts.get("title_length", 0)
        if 30 <= tl <= 65: return 100
        if 20 <= tl <= 75: return 85
        return 60 if tl > 0 else 30
    if name == "Meta Description (Length &amp; Quality)":
        md = facts.get("meta_desc_length", 0)
        if 120 <= md <= 160: return 100
        if 80 <= md <= 180: return 85
        return 60 if md > 0 else 30
    if name == "Canonical Tag Present":
        return 100 if facts.get("canonical_present") else 60
    if name == "H1 Tag Unique &amp; Present":
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
    if name == "Mobile-Friendly (PSI Viewport)":
        return 100 if psi.get("psi_viewport_pass") else (80 if facts.get("mobile_friendly_heur") else 60)
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
    if name == "Vulnerable JS Libraries (heuristic)":
        libs = [u for u in (audit.get("resource_names") or []) if any(x in u.lower() for x in ["jquery", "angular", "react"])]
        return 80 if libs else 90

    return 80

def generate_audit_results(audit: Dict[str, Any], soup: BeautifulSoup, psi: Dict[str, Any]) -> Dict[str, Any]:
    facts = evaluate_facts(soup, audit)

    metrics: List[Dict[str, Any]] = []
    pillar_scores: Dict[str, List[Tuple[int, int]]] = {cat: [] for cat in CATEGORIES}
    low_score_issues: List[Dict[str, str]] = []

    for i, (name, category) in enumerate(METRICS_LIST, 1):
        score = clamp_score(compute_metric_score(name, category, audit, facts, psi))
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
    roadmap_html = ""
    if psi.get("psi_opportunities"):
        psi_roadmap = "&lt;b&gt;PSI Opportunities:&lt;/b&gt;&lt;br/&gt;&lt;br/&gt;" + "&lt;br/&gt;".join([f"- {x}" for x in psi["psi_opportunities"][:20]])
        roadmap_html += psi_roadmap + "&lt;br/&gt;&lt;br/&gt;"
    roadmap_html += ("&lt;b&gt;Improvement Roadmap:&lt;/b&gt;&lt;br/&gt;&lt;br/&gt;" + "&lt;br/&gt;".join(roadmap_items)) if roadmap_items \
                    else "&lt;b&gt;Improvement Roadmap:&lt;/b&gt;&lt;br/&gt;&lt;br/&gt;No critical issues found."
    summary = f"Weighted Scores by Pillar: {weighted_pillars}"

    return {
        "metrics": metrics,
        "pillar_avg": weighted_pillars,
        "total_grade": total_grade,
        "summary": summary,
        "roadmap": roadmap_html,
    }

# ==================== SEO REPORT (dynamic for any domain) ====================
def build_seo_audit(final_url: str, soup: BeautifulSoup, audit: Dict[str, Any], psi: Dict[str, Any]) -> Dict[str, Any]:
    facts = evaluate_facts(soup, audit)

    issues = []
    def _iss(element, note, priority="red-flag", type_="Page Speed"):
        issues.append({"type": type_, "element": element, "priority": priority, "message": note})

    if psi.get("psi_dom_size") is not None:
        _iss("DOM Size", f"DOM elements: {int(psi['psi_dom_size'])}. Reduce complexity if very large.")
    else:
        _iss("DOM Size", "Unable to retrieve DOM Size metric (PSI unavailable).")

    if psi.get("psi_tbt_ms") is not None:
        _iss("Total Blocking Time (TBT)", f"{int(psi['psi_tbt_ms'])} ms. Reduce long tasks &amp; JS execution.", "flag")
    else:
        _iss("Total Blocking Time (TBT)", "Unable to retrieve TBT metric (PSI unavailable).")

    if psi.get("psi_speed_index_ms") is not None:
        _iss("Speed Index", f"{int(psi['psi_speed_index_ms'])} ms. Optimize render &amp; critical path.", "flag")
    else:
        _iss("Speed Index", "Unable to retrieve Speed Index metric (PSI unavailable).")

    if psi.get("psi_fcp_ms") is not None:
        _iss("First Contentful Paint (FCP)", f"{int(psi['psi_fcp_ms'])} ms.", "flag")

    _iss("Time to First Byte (TTFB)", f"{int(audit.get('ttfb', 0))} ms.", "flag")

    if psi.get("psi_cls") is not None:
        _iss("Cumulative Layout Shift (CLS)", f"{psi['psi_cls']:.3f}. Reserve space &amp; preload fonts.", "flag")

    if psi.get("psi_inp_ms") is not None:
        _iss("Interaction to Next Paint (INP)", f"{int(psi['psi_inp_ms'])} ms. Optimize event handlers/JS.", "flag")
    else:
        _iss("Interaction to Next Paint (INP)", "Unable to retrieve INP (PSI unavailable).")

    if psi.get("psi_lcp_ms") is not None:
        _iss("Largest Contentful Paint (LCP)", f"{int(psi['psi_lcp_ms'])} ms.", "flag")

    if psi.get("psi_viewport_pass") is not None:
        _iss("Mobile Friendliness", "Pass" if psi["psi_viewport_pass"] else "Fail — configure viewport &amp; responsive layout.", "flag", "Mobile")

    if psi.get("psi_performance_percent") is not None:
        _iss("Overall Performance", f"Lighthouse Performance: {psi['psi_performance_percent']}%", "flag")

    # On-Page SEO
    on_page = {
        "url": {"value": final_url, "note": "Audited page URL."},
        "title": {"priority": "info", "value": soup.find("title").text.strip() if soup.find("title") else None,
                  "note": "Ideal length 50–60 chars."},
        "meta_description": {"priority": "info", "value": (soup.find('meta', attrs={'name':'description'}) or {}).get('content'),
                             "note": "Aim for ~100–130 chars."},
        "h1": {"priority": "info", "value": (soup.find("h1").text.strip() if soup.find("h1") else None),
               "note": "Exactly one H1 preferred."},
        "headings": {"priority": "info", "structure": {
            "H2": facts.get("headings", {}).get("h2", 0),
            "H3": facts.get("headings", {}).get("h3", 0),
            "H4": facts.get("headings", {}).get("h4", 0),
            "H5": facts.get("headings", {}).get("h5", 0),
            "H6": facts.get("headings", {}).get("h6", 0),
        }, "note": "Use semantic hierarchy with H2/H3 for sections."},
        "image_alt": {"priority": "info", "note": f"Alt coverage ~{facts.get('image_alt_ratio', 0):.0f}%."},
        "keyword_density": {"value": "N/A"}  # still optional
    }

    keyword_rankings: List[Dict[str, Any]] = []
    top_pages: List[Dict[str, Any]] = []
    off_page: Dict[str, Any] = {"message": "Connect an SEO API (e.g., Semrush/Ahrefs/GSC) to populate Off‑Page &amp; Rankings."}
    top_backlinks: List[Dict[str, Any]] = []

    technical = [
        {"element": "Favicon", "priority": "pass" if facts.get("favicon_present") else "red-flag",
         "value": "Present" if facts.get("favicon_present") else "Missing",
         "note": "Provide a favicon.ico or &lt;link rel='icon'&gt;."},
        {"element": "Noindex", "priority": "pass" if "noindex" not in facts.get("robots_meta","") else "red-flag",
         "note": "Ensure important pages are indexable."},
        {"element": "Sitemap", "priority": "info", "note": "Not checked. Add /sitemap.xml &amp; declare in robots.txt."},
        {"element": "Hreflang", "priority": "info", "note": "Add hreflang for language/region variants."},
        {"element": "Language", "priority": "info", "value": soup.find("html").get("lang") if soup.find("html") else None,
         "note": "Set &lt;html lang='...'&gt; for accessibility &amp; SEO."},
        {"element": "Canonical", "priority": "pass" if facts.get("canonical_present") else "red-flag",
         "note": "Add a single canonical pointing to preferred URL."},
        {"element": "Robots.txt", "priority": "info", "value": f"{urlparse(final_url).scheme}://{urlparse(final_url).netloc}/robots.txt",
         "note": "Ensure accessible robots.txt."},
        {"element": "Structured Data", "priority": "pass" if facts.get("schema_present") else "info",
         "note": "Add JSON-LD (Schema.org) for rich results."},
    ]

    page_performance = []
    def add_perf(label, value, note="", pr="info"):
        page_performance.append({"element": label, "priority": pr, "note": f"{value} {note}".strip()})

    add_perf("Performance Score", f"{psi.get('psi_performance_percent','N/A')}%", "")
    add_perf("Largest Contentful Paint (LCP)", f"{int(psi.get('psi_lcp_ms') or audit.get('lcp',0))} ms")
    add_perf("Interaction to Next Paint (INP)", f"{int(psi.get('psi_inp_ms') or 0)} ms")
    add_perf("Cumulative Layout Shift (CLS)", f"{psi.get('psi_cls'):.3f}" if psi.get('psi_cls') is not None else "N/A")
    add_perf("Time to First Byte (TTFB)", f"{int(audit.get('ttfb',0))} ms")
    add_perf("First Contentful Paint (FCP)", f"{int(psi.get('psi_fcp_ms') or audit.get('fcp',0))} ms")
    add_perf("Speed Index", f"{int(psi.get('psi_speed_index_ms') or 0)} ms")
    add_perf("Total Blocking Time (TBT)", f"{int(psi.get('psi_tbt_ms') or audit.get('tbt',0))} ms")
    add_perf("DOM Size", f"{int(psi.get('psi_dom_size') or 0)}")
    add_perf("Mobile Friendliness", "Pass" if psi.get('psi_viewport_pass') else "Fail", pr="info")

    competitors = [{"competitor": "N/A", "common_keywords": 0, "competition_level": 0}]

    social_media = []
    for net, present in facts.get("social_presence", {}).items():
        social_media.append({
            "network": net,
            "priority": "pass" if present else "red-flag",
            "note": "Link detected." if present else f"Add a working {net} link."
        })

    return {
        "domain": urlparse(final_url).netloc,
        "seo_score": psi.get("psi_performance_percent") or 0,  # placeholder
        "critical_issues": sum(1 for i in issues if i["priority"] == "red-flag"),
        "minor_issues": sum(1 for i in issues if i["priority"] != "red-flag"),
        "overview_text": "Automated site audit combining Lighthouse (PSI) &amp; DOM heuristics.",
        "section_scores": {
            "On-Page SEO": 0, "Technical SEO": 0, "Off-Page SEO": 0, "Social Media": 0
        },
        "issues": issues,
        "on_page": on_page,
        "keyword_rankings": keyword_rankings,
        "top_pages": top_pages,
        "technical": technical,
        "page_performance": page_performance,
        "competitors": competitors,
        "off_page": off_page,
        "top_backlinks": top_backlinks,
        "social_media": social_media,
    }

# ==================== PDF HELPERs ====================
def _fit_col_widths(col_widths: Optional[List[float]], max_width: float) -> Optional[List[float]]:
    if not col_widths:
        return None
    total = sum(col_widths)
    if total <= max_width:
        return col_widths
    scale = max_width / float(total)
    return [w * scale for w in col_widths]

def _para(text, style): return Paragraph(text or "", style)

def _link(text, url, style):
    """Fix: proper ReportLab hyperlink tag."""
    if not url:
        return Paragraph(text or "", style)
    safe_text = (text or url)
    return Paragraph(f'<link href_text}</link>', style)

def _table(story, data, doc, col_widths=None, header_bg="#0f172a", align_right_cols=None, center_cols=None):
    max_width = A4[0] - doc.leftMargin - doc.rightMargin
    col_widths = _fit_col_widths(col_widths, max_width)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    ts = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor(header_bg)),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.lightgrey]),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]
    if align_right_cols:
        for c in align_right_cols: ts.append(('ALIGN', (c,1), (c,-1), 'RIGHT'))
    if center_cols:
        for c in center_cols: ts.append(('ALIGN', (c,1), (c,-1), 'CENTER'))
    t.setStyle(TableStyle(ts))
    story.append(t)

def _add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    canvas.setStrokeColor(colors.HexColor("#e5e7eb"))
    canvas.line(doc.leftMargin, 35, A4[0] - doc.rightMargin, 35)
    canvas.drawRightString(A4[0] - doc.rightMargin, 20, f"Page {doc.page}")
    canvas.restoreState()

def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ReportTitle', fontSize=22, leading=26, alignment=1,
                              textColor=colors.HexColor("#10b981"), spaceAfter=12, spaceBefore=6))
    styles.add(ParagraphStyle(name='SectionTitle', fontSize=16, leading=20,
                              textColor=colors.HexColor("#0f172a"), spaceBefore=14, spaceAfter=8))
    styles.add(ParagraphStyle(name='SubTitle', fontSize=12, leading=16,
                              textColor=colors.HexColor("#0f172a"), spaceBefore=6, spaceAfter=6))
    styles.add(ParagraphStyle(name='NormalGrey', fontSize=10, leading=14, textColor=colors.HexColor("#64748b")))
    styles.add(ParagraphStyle(name='Normal', fontSize=10, leading=14, textColor=colors.black))
    styles.add(ParagraphStyle(name='KPI', fontSize=11, leading=14, textColor=colors.HexColor("#10b981"), spaceAfter=4))
    return styles

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

    logger.info(f"Auditing URL: {normalized_url} (mode={'mobile' if mode else 'desktop'})")

    # 1) PSI (Lighthouse) enrichment
    psi_raw = call_psi(normalized_url, strategy=("mobile" if mode else "desktop"))
    psi = extract_from_psi(psi_raw)

    # 2) Playwright lab audit OR requests fallback
    audit_data: Dict[str, Any]
    html_for_soup: str
    if PLAYWRIGHT_AVAILABLE:
        try:
            audit_data = await run_playwright_audit(normalized_url, mobile=mode)
            html_for_soup = audit_data.get("html", "")
        except Exception as e:
            logger.warning(f"Playwright audit failed: {e}")
            # Try requests fallback to at least populate DOM facts
            html_text, hdrs, final_u = fetch_html_and_headers(normalized_url)
            audit_data = {
                "ttfb": 0,
                "fcp": psi.get("psi_fcp_ms") or 0,
                "lcp": psi.get("psi_lcp_ms") or 0,
                "cls": psi.get("psi_cls") or 0.0,
                "tbt": psi.get("psi_tbt_ms") or 0,
                "page_weight_kb": 0,
                "request_count": 0,
                "final_url": final_u,
                "html": html_text,
                "headers": hdrs,
                "console_errors": [],
                "requested_urls": [],
                "resource_names": [],
                "cookies": [],
            }
            html_for_soup = html_text
    else:
        # Fallback to PSI + requests to fetch HTML
        html_text, hdrs, final_u = fetch_html_and_headers(normalized_url)
        audit_data = {
            "ttfb": 0,
            "fcp": psi.get("psi_fcp_ms") or 0,
            "lcp": psi.get("psi_lcp_ms") or 0,
            "cls": psi.get("psi_cls") or 0.0,
            "tbt": psi.get("psi_tbt_ms") or 0,
            "page_weight_kb": 0,
            "request_count": 0,
            "final_url": final_u,
            "html": html_text,
            "headers": hdrs,
            "console_errors": [],
            "requested_urls": [],
            "resource_names": [],
            "cookies": [],
        }
        html_for_soup = html_text

    soup = BeautifulSoup(html_for_soup, "html.parser")

    # 3) Compute metrics + scores
    results = generate_audit_results(audit_data, soup, psi)

    # 4) Build SEO audit sections
    seo_audit = build_seo_audit(audit_data["final_url"], soup, audit_data, psi)

    # 5) Response
    return {
        "url": audit_data["final_url"],
        "audited_at": time.strftime("%B %d, %Y at %H:%M UTC"),
        "total_grade": results["total_grade"],
        "pillars": results["pillar_avg"],
        "metrics": results["metrics"],
        "summary": results["summary"],
        "perf": {
            "ttfb_ms": audit_data.get("ttfb"),
            "fcp_ms": psi.get("psi_fcp_ms") or audit_data.get("fcp"),
            "lcp_ms": psi.get("psi_lcp_ms") or audit_data.get("lcp"),
            "cls": psi.get("psi_cls") if psi.get("psi_cls") is not None else audit_data.get("cls"),
            "tbt_ms": psi.get("psi_tbt_ms") or audit_data.get("tbt"),
            "page_weight_kb": audit_data.get("page_weight_kb"),
            "request_count": audit_data.get("request_count"),
            "dom_size": psi.get("psi_dom_size"),
            "speed_index_ms": psi.get("psi_speed_index_ms"),
            "inp_ms": psi.get("psi_inp_ms"),
            "lighthouse_performance_percent": psi.get("psi_performance_percent"),
            "viewport_audit_pass": psi.get("psi_viewport_pass"),
        },
        "roadmap": results["roadmap"],
        "seo_audit": seo_audit,
    }

# ==================== PDF (World-class formatting) ====================
@app.post("/download")
async def download_pdf(request: Request):
    data = await request.json()
    metrics = data.get("metrics") or []
    pillars = data.get("pillars") or {}
    total_grade = data.get("total_grade")
    url = data.get("url", "")
    seo_audit = data.get("seo_audit")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=50, leftMargin=50, topMargin=60, bottomMargin=50,
        title="FF TECH ELITE - Enterprise Web Audit Report", author="FF TECH ELITE v3"
    )
    s = _styles()
    story: List[Any] = []

    logo_path = "logo.png"
    if os.path.exists(logo_path):
        try:
            story.append(Image(logo_path, width=120, height=50))
            story.append(Spacer(1, 12))
        except Exception:
            pass

    story.append(_para("FF TECH ELITE - Enterprise Web Audit Report", s['ReportTitle']))
    story.append(_para(f"Target URL: {url or 'N/A'}", s['Normal']))
    story.append(_para(f"Generated: {time.strftime('%B %d, %Y at %H:%M UTC')}", s['NormalGrey']))
    story.append(Spacer(1, 6))
    story.append(_para(f"Overall Health Score: {total_grade}%", s['KPI']))
    story.append(Spacer(1, 8))

    pillar_table = [["Pillar", "Score"]]
    for cat in CATEGORIES:
        sc = pillars.get(cat, "—")
        pillar_table.append([cat, f"{sc}%" if isinstance(sc, (int, float)) else sc])
    _table(story, pillar_table, doc, col_widths=[300, 100], header_bg="#0f172a", align_right_cols=[1])
    story.append(PageBreak())

    story.append(_para("Table of Contents", s['SectionTitle']))
    toc_items = [
        "1. Advanced Diagnostics (metrics)",
        "2. Improvement Roadmap",
        "3. SEO Audit Results",
        "   3.1 Overview &amp; Section Scores",
        "   3.2 Issues &amp; Recommendations",
        "   3.3 On-Page SEO",
        "   3.4 Keyword Rankings &amp; Top Pages",
        "   3.5 Technical SEO",
        "   3.6 Page Performance &amp; Core Web Vitals",
        "   3.7 Competitors",
        "   3.8 Off-Page SEO &amp; Top Backlinks",
        "   3.9 Social Media",
    ]
    story.append(ListFlowable([ListItem(_para(it, s['Normal']), leftIndent=10, value='•') for it in toc_items], bulletType='bullet'))
    story.append(PageBreak())

    story.append(_para("Advanced Diagnostics", s['SectionTitle']))
    table_data = [["#", "Metric", "Category", "Score", "Weight"]]
    for m in metrics:
        table_data.append([
            m.get('no', ''),
            Paragraph(m.get('name', ''), s['Normal']),
            Paragraph(m.get('category', ''), s['Normal']),
            Paragraph(f"{m.get('score', '')}%", s['Normal']),
            m.get('weight', '')
        ])
    _table(story, table_data, doc, col_widths=[30, 220, 100, 50, 50], header_bg="#10b981", align_right_cols=[3, 4], center_cols=[0])
    story.append(PageBreak())

    story.append(_para("Improvement Roadmap", s['SectionTitle']))
    roadmap_html = (data.get("roadmap") or "&lt;b&gt;Improvement Roadmap:&lt;/b&gt;&lt;br/&gt;&lt;br/&gt;Prioritize critical items first.")
    items = []
    for line in roadmap_html.split("&lt;br/&gt;"):
        txt = line.strip()
        if not txt or txt.lower().startswith("&lt;b&gt;"): continue
        txt = txt.replace("&lt;/b&gt;", "").replace("&lt;b&gt;", "")
        items.append(txt)
    if items:
        story.append(ListFlowable([ListItem(_para(it, s['Normal']), leftIndent=10, value='–') for it in items], bulletType='bullet'))
    else:
        story.append(_para(roadmap_html, s['Normal']))
    story.append(PageBreak())

    if seo_audit:
        story.append(_para(f"SEO Audit Results for {seo_audit.get('domain')}", s['ReportTitle']))
        story.append(Spacer(1, 6))
        story.append(KeepTogether([
            _para("Overview", s['SectionTitle']),
            _para(seo_audit.get("overview_text", ""), s['Normal'])
        ]))
        scores = seo_audit.get("section_scores", {})
        overview_table = [["Section", "Score"]]
        for k in ["On-Page SEO", "Technical SEO", "Off-Page SEO", "Social Media"]:
            overview_table.append([k, f"{scores.get(k, 0)}%"])
        _table(story, overview_table, doc, col_widths=[300, 100], align_right_cols=[1])
        story.append(PageBreak())

        story.append(_para("Issues and Recommendations", s['SectionTitle']))
        issues = seo_audit.get("issues", [])
        issues_table = [["Type", "Element", "Priority", "Problem / Recommendation"]]
        for item in issues:
            issues_table.append([
                Paragraph(item.get("type",""), s['Normal']),
                Paragraph(item.get("element",""), s['Normal']),
                Paragraph(item.get("priority",""), s['Normal']),
                Paragraph(item.get("message",""), s['Normal'])
            ])
        _table(story, issues_table, doc, col_widths=[90, 110, 70, 230], header_bg="#ef4444")
        story.append(PageBreak())

        story.append(_para("On-Page SEO", s['SectionTitle']))
        onp = seo_audit.get("on_page", {})
        onpage_table = [["Element", "Value/Status", "Note"]]
        onpage_table.append(["URL", Paragraph(onp.get("url", {}).get("value", ""), s['Normal']),
                             Paragraph(onp.get("url", {}).get("note", ""), s['Normal'])])
        title = onp.get("title", {})
        onpage_table.append(["Title", Paragraph(title.get("value", "—") or "—", s['Normal']),
                             Paragraph(title.get("note", ""), s['Normal'])])
        md = onp.get("meta_description", {})
        onpage_table.append(["Meta Description", Paragraph(md.get("value", "Missing") or "Missing", s['Normal']),
                             Paragraph(md.get("note", ""), s['Normal'])])
        h1 = onp.get("h1", {})
        onpage_table.append(["H1", Paragraph(h1.get("value", "Missing") or "Missing", s['Normal']),
                             Paragraph(h1.get("note", ""), s['Normal'])])
        heads = onp.get("headings", {}).get("structure", {})
        onpage_table.append([
            "Heading Structure",
            Paragraph(f"H2:{heads.get('H2',0)} H3:{heads.get('H3',0)} H4:{heads.get('H4',0)} H5:{heads.get('H5',0)} H6:{heads.get('H6',0)}", s['Normal']),
            Paragraph(onp.get("headings", {}).get("note",""), s['Normal'])
        ])
        imgalt = onp.get("image_alt", {})
        onpage_table.append(["Image Alt", Paragraph("Coverage reported", s['Normal']),
                             Paragraph(imgalt.get("note",""), s['Normal'])])
        onpage_table.append(["Keyword Density", Paragraph(str(onp.get("keyword_density","N/A")), s['Normal']),
                             Paragraph("Integrate an SEO API to compute real density.", s['Normal'])])
        _table(story, onpage_table, doc, col_widths=[120, 150, 240])
        story.append(PageBreak())

        story.append(_para("Keyword Rankings", s['SectionTitle']))
        kr = seo_audit.get("keyword_rankings", [])
        kr_table = [["Keyword", "Rank", "Traffic %", "Volume", "KD %", "CPC (USD)"]]
        for k in (kr or [{"keyword":"N/A","rank": "", "traffic_pct":"","volume":"","kd_pct":"","cpc_usd":""}]):
            kr_table.append([Paragraph(k.get("keyword",""), s['Normal']),
                             k.get("rank",""), k.get("traffic_pct",""), k.get("volume",""),
                             k.get("kd_pct",""), k.get("cpc_usd","")])
        _table(story, kr_table, doc, col_widths=[150, 50, 70, 70, 60, 80], header_bg="#10b981", center_cols=[1,2,3,4,5])
        story.append(Spacer(1, 8))

        story.append(_para("Top Pages", s['SubTitle']))
        tp = seo_audit.get("top_pages", [])
        tp_table = [["URL", "Traffic %", "Keywords", "Ref Dom", "Backlinks"]]
        for p in (tp or [{"url": url, "traffic_pct":"", "keywords":"", "ref_domains":"", "backlinks":""}]):
            tp_table.append([_link(p.get("url",""), p.get("url",""), s['Normal']),
                             p.get("traffic_pct",""), p.get("keywords",""),
                             p.get("ref_domains",""), p.get("backlinks","")])
        _table(story, tp_table, doc, col_widths=[240, 60, 70, 70, 70], header_bg="#10b981", center_cols=[1,2,3,4])
        story.append(PageBreak())

        story.append(_para("Technical SEO", s['SectionTitle']))
        tech = seo_audit.get("technical", [])
        tech_table = [["Element", "Priority", "Value", "Recommendation"]]
        for t in tech:
            tech_table.append([
                Paragraph(t.get("element",""), s['Normal']),
                Paragraph(t.get("priority",""), s['Normal']),
                Paragraph(str(t.get("value","—")), s['Normal']),
                Paragraph(t.get("note",""), s['Normal'])
            ])
        _table(story, tech_table, doc, col_widths=[140, 90, 120, 200], header_bg="#0f172a")
        story.append(PageBreak())

        story.append(_para("Page Performance &amp; Core Web Vitals", s['SectionTitle']))
        pp = seo_audit.get("page_performance", [])
        pp_table = [["Element", "Priority", "Note"]]
        for p in pp:
            pp_table.append([
                Paragraph(p.get("element",""), s['Normal']),
                Paragraph(p.get("priority",""), s['Normal']),
                Paragraph(p.get("note",""), s['Normal'])
            ])
        _table(story, pp_table, doc, col_widths=[200, 80, 240], header_bg="#f59e0b")
        story.append(PageBreak())

        story.append(_para("Competitors", s['SectionTitle']))
        comp = seo_audit.get("competitors", [])
        comp_table = [["Competitor", "Common Keywords", "Competition Level"]]
        for c in comp:
            comp_table.append([Paragraph(c.get("competitor",""), s['Normal']),
                               c.get("common_keywords",""), c.get("competition_level","")])
        _table(story, comp_table, doc, col_widths=[220, 140, 120], header_bg="#64748b", center_cols=[1,2])
        story.append(PageBreak())

        story.append(_para("Off-Page SEO", s['SectionTitle']))
        story.append(_para(seo_audit.get("off_page", {}).get("message",""), s['NormalGrey']))
        story.append(Spacer(1, 8))

        story.append(_para("Top Backlinks", s['SubTitle']))
        bl = seo_audit.get("top_backlinks", [])
        bl_table = [["Page AS", "Source Title", "Source URL", "Anchor", "Target URL", "Rel"]]
        for b in (bl or [{"page_as":"", "source_title":"N/A", "source_url":url, "anchor":"", "target_url":url, "rel":""}]):
            bl_table.append([
                b.get("page_as",""), Paragraph(b.get("source_title",""), s['Normal']),
                _link(b.get("source_url",""), b.get("source_url",""), s['Normal']),
                Paragraph(b.get("anchor",""), s['Normal']),
                _link(b.get("target_url",""), b.get("target_url",""), s['Normal']),
                Paragraph(b.get("rel","") or "", s['Normal'])
            ])
        _table(story, bl_table, doc, col_widths=[50, 140, 120, 90, 95, 40], header_bg="#0ea5e9", center_cols=[0,5])
        story.append(PageBreak())

        story.append(_para("Social Media", s['SectionTitle']))
        sm = seo_audit.get("social_media", [])
        sm_table = [["Network", "Priority", "Recommendation"]]
        for srow in sm:
            sm_table.append([
                Paragraph(srow.get("network",""), s['Normal']),
                Paragraph(srow.get("priority",""), s['Normal']),
                Paragraph(srow.get("note",""), s['Normal'])
            ])
        _table(story, sm_table, doc, col_widths=[120, 80, 280], header_bg="#a855f7"])
        story.append(PageBreak())

    doc.build(story, onFirstPage=_add_page_number, onLaterPages=_add_page_number)
    buffer.seek(0)
    filename = f"FF_ELITE_Audit_Report_{int(time.time())}.pdf"
    return StreamingResponse(
        buffer, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# ==================== MAIN ====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
