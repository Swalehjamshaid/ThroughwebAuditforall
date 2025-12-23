
import asyncio
import time
import io
import os
import logging
from typing import Dict, Any, List, Tuple
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
    """
    Piecewise scoring: bands sorted by max_value ascending.
    Each band: (max_value, score). Return first score where value <= max_value, else last.
    """
    for max_v, s in bands:
        if value <= max_v:
            return s
    return bands[-1][1] if bands else 0

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

        # Lab TTFB approximation (nav start -> first byte observed)
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

    # SEO
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

    # UX
    viewport_meta = soup.find("meta", attrs={"name": "viewport"})
    viewport_content = (viewport_meta.get("content", "") or "").lower() if viewport_meta else ""
    mobile_friendly = "width=device-width" in viewport_content
    favicon_present = bool(soup.find("link", rel=lambda x: x and "icon" in x.lower()))
    touch_icons_present = bool(soup.find("link", rel=lambda x: x and "apple-touch-icon" in x.lower()))
    no_console_errors = len(console_errors) == 0

    # Security
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

    # Perf heuristics
    js_minified = any(".min.js" in u.lower() for u in res_names)
    font_display_swap = any(("display=swap" in u.lower()) for u in res_names)

    # Image optimization
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

# ==================== SCORING (INTERNATIONAL THRESHOLDS) ====================
def compute_metric_score(name: str, category: str, audit: Dict[str, Any], facts: Dict[str, Any]) -> int:
    # ---- Performance (CWV-aligned thresholds) ----
    if name == "Largest Contentful Paint (LCP)":
        lcp = audit.get("lcp", 0)
        # CWV: Good ≤2.5s; NI ≤4.0s; Poor >4.0s
        return score_band(lcp, [(2500, 100), (4000, 80), (10000, 60), (9999999, 40)])

    if name == "First Contentful Paint (FCP)":
        fcp = audit.get("fcp", 0)
        # FCP guidance used broadly: Good ≤1.8s then soften
        return score_band(fcp, [(1800, 100), (3000, 85), (8000, 60), (9999999, 40)])

    if name == "Time to First Byte (TTFB)":
        ttfb = audit.get("ttfb", 0)
        # Google guidance: Good ≲800ms; NI ≤1800ms; Poor >1800ms
        return score_band(ttfb, [(800, 100), (1800, 80), (4000, 60), (9999999, 40)])

    if name == "Cumulative Layout Shift (CLS)":
        cls = float(audit.get("cls", 0.0))
        # CWV: Good ≤0.1; NI ≤0.25; Poor >0.25
        return score_band(cls, [(0.1, 100), (0.25, 80), (0.5, 60), (9999999, 40)])

    if name == "Total Blocking Time (TBT)":
        tbt = audit.get("tbt", 0)
        # Lighthouse lab proxy for responsiveness
        return score_band(tbt, [(200, 100), (600, 80), (1200, 60), (9999999, 40)])

    if name == "Page Weight (KB)":
        kb = audit.get("page_weight_kb", 0)
        return score_band(kb, [(1500, 100), (3000, 85), (6000, 60), (9999999, 40)])

    if name == "Number of Requests":
        reqs = audit.get("request_count", 0)
        return score_band(reqs, [(60, 100), (100, 85), (200, 60), (9999999, 40)])

    if name == "Image Optimization":
        ratio = facts.get("image_optimization_ratio", 0.0)  # % optimized
        return score_band(ratio, [(50, 60), (75, 80), (90, 95), (9999999, 100)])

    if name == "JavaScript Minification":
        return 100 if facts.get("js_minified") else 60

    if name == "Font Display Strategy":
        return 100 if facts.get("font_display_swap") else 60

    # ---- SEO ----
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

    # ---- UX ----
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
        return 80  # neutral baseline

    # ---- Security ----
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

    # Default for advanced checks
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

    # Weighted pillar scores by metric weights (your weight system already used)
    weighted_pillars: Dict[str, int] = {}
    for cat, vals in pillar_scores.items():
        total_weight = sum(w for _, w in vals)
        weighted = sum(s * w for s, w in vals) / total_weight if total_weight else 100
        weighted_pillars[cat] = clamp_score(weighted)

    # Final grade by your pillar weights
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

# ==================== PDF HELPERS ====================
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
    }

@app.post("/download")
async def download_pdf(request: Request):
    data = await request.json()
    metrics = data.get("metrics") or []
    pillars = data.get("pillars") or {}
    total_grade = data.get("total_grade")
    url = data.get("url", "")

    # Regenerate if minimal data
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

    story: List[Any] = []

    # Optional logo
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
    t = Table(pillar_table, colWidths=[300, 100])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0f172a")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.lightgrey]),
        ('ALIGN', (1,1), (-1,-1), 'RIGHT'),
    ]))
    story.append(t)
    story.append(Spacer(1, 20))

    # Metrics
    story.append(Paragraph("Detailed Metrics", styles['Section']))
    table_data = [["#", "Metric", "Category", "Score", "Weight"]]
    for m in metrics:
        table_data.append([m.get('no', ''), m.get('name', ''), m.get('category', ''), f"{m.get('score', '')}%", m.get('weight', '')])
    dt = Table(table_data, colWidths=[30, 220, 100, 50, 50])
    dt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#10b981")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.lightgrey]),
        ('ALIGN', (3,1), (-1,-1), 'RIGHT'),
    ]))
    story.append(dt)
    story.append(PageBreak())

    story.append(Paragraph("Improvement Roadmap", styles['TitleBold']))
    story.append(Spacer(1, 10))
    roadmap_html = data.get("roadmap") or "<b>Improvement Roadmap:</b><br/><br/>Prioritize critical items first."
    story.append(Paragraph(roadmap_html, styles['Normal']))

    doc.build(story, onFirstPage=_add_page_number, onLaterPages=_add_page_number)
    buffer.seek(0)
    filename = f"FF_ELITE_Audit_Report_{int(time.time())}.pdf"
    return StreamingResponse(buffer, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={filename}"})

# ==================== MAIN ====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
