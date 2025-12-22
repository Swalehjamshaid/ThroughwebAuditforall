
# app.py
import io
import os
import re
import time
from typing import Dict, List, Tuple

import requests
import urllib3
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, JSONResponse

# PDF using reportlab (more robust than fpdf in many containers)
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI(title="FF TECH ELITE")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------- CATEGORY IMPACT (Multipliers) ---------------------------
CATEGORY_IMPACT = {
    "Technical SEO": 1.5,   # Critical
    "Security": 1.4,        # Critical
    "Performance": 1.3,     # High
    "On-Page SEO": 1.2,     # High
    "User Experience & Mobile": 1.1,
    "Accessibility": 0.8,
    "Advanced SEO & Analytics": 0.7,
}

# --------------------------- CHECKS & WEIGHTS (Deterministic) ------------------------
CATEGORIES: Dict[str, List[Tuple[str, int]]] = {
    "Technical SEO": [
        ("HTTPS Enabled", 10), ("Title Tag Present", 10), ("Meta Description Present", 10),
        ("Canonical Tag Present", 8), ("Robots.txt Accessible", 7), ("XML Sitemap Exists", 7),
        ("Structured Data Markup", 6), ("Hreflang Implementation", 5),
        ("Server Response 200 OK", 10),
    ],
    "On-Page SEO": [
        ("Single H1 Tag", 10), ("Heading Structure Correct (H2/H3)", 8),
        ("Image ALT Coverage ≥ 90%", 8), ("Internal Linking Present", 6),
        ("Meta Title Length Optimal", 5), ("Meta Description Length Optimal", 5),
    ],
    "Performance": [
        ("TTFB < 200ms", 10), ("Page Size < 2 MB", 9), ("Images Lazy-Loaded", 8),
        ("Min Blocking Scripts", 7), ("Resource Compression (gzip/brotli)", 7),
    ],
    "Accessibility": [
        ("Alt Text Coverage", 8), ("ARIA Roles Present", 6), ("Form Labels Present", 5),
        ("Semantic HTML Tags Used", 6),
    ],
    "Security": [
        ("HTTPS Enforced (HTTP→HTTPS)", 10), ("HSTS Configured", 8),
        ("Content Security Policy", 7), ("X-Frame-Options/Frame-Ancestors", 6),
        ("X-Content-Type-Options", 6), ("Referrer-Policy", 5),
    ],
    "User Experience & Mobile": [
        ("Viewport Meta Present", 9), ("Mobile Responsive Hints", 7),
        ("Non-Intrusive Scripts (count)", 6),
    ],
    "Advanced SEO & Analytics": [
        ("Analytics Tracking Installed", 9), ("Search Console Connected (heuristic)", 7),
        ("Social Meta Tags Present", 5), ("Sitemap Submitted (heuristic)", 6),
    ],
}

# --------------------------- Helper Utilities ---------------------------------------
def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url

def extract_host(url: str) -> str:
    # Return scheme://host (no path)
    m = re.match(r"^(https?://[^/]+)", url)
    return m.group(1) if m else url

def safe_get(url: str, timeout: int = 15, allow_redirects: bool = True):
    return requests.get(
        url, timeout=timeout, verify=False, allow_redirects=allow_redirects,
        headers={"User-Agent": "FFTechElite/3.1"}
    )

def measure_ttfb(url: str) -> float:
    start = time.time()
    r = safe_get(url)
    ttfb_ms = (time.time() - start) * 1000.0
    return r, ttfb_ms

def text_length_optimal(text: str, low: int, high: int) -> bool:
    length = len(text or "")
    return low <= length <= high

def count_blocking_scripts(soup: BeautifulSoup) -> int:
    # Blocking = <script> without async/defer attributes
    count = 0
    for s in soup.find_all("script", src=True):
        if not s.has_attr("async") and not s.has_attr("defer"):
            count += 1
    return count

def is_gzip_brotli(headers: Dict[str, str]) -> bool:
    enc = headers.get("Content-Encoding", "") or headers.get("content-encoding", "")
    return ("gzip" in enc.lower()) or ("br" in enc.lower())

def has_analytics(soup: BeautifulSoup) -> bool:
    # heuristic: look for GA/GTM snippets
    code = str(soup)
    return any([
        "gtag(" in code, "googletagmanager.com" in code, "google-analytics.com" in code,
        "dataLayer" in code
    ])

def has_social_meta(soup: BeautifulSoup) -> bool:
    return bool(
        soup.find("meta", property="og:title") or
        soup.find("meta", property="og:description") or
        soup.find("meta", name="twitter:card")
    )

def has_media_queries(soup: BeautifulSoup) -> bool:
    # Heuristic: presence of responsive frameworks or viewport + responsive classes
    if soup.find("meta", {"name": "viewport"}):
        return True
    # Tailwind/Bootstrap classes (very rough heuristic)
    code = str(soup)
    return any(k in code for k in ["container", "grid", "col-", "sm:", "md:", "lg:"])

def check_http_enforce_https(host: str) -> bool:
    # Try http scheme and see if first redirect goes to https
    http_url = re.sub(r"^https://", "http://", host)
    try:
        r = requests.get(http_url, timeout=10, verify=False, allow_redirects=False)
        loc = r.headers.get("Location", "") or r.headers.get("location", "")
        return ("https://" in loc) or (r.is_redirect and "https://" in loc)
    except Exception:
        return False

def robots_accessible(host: str) -> bool:
    try:
        r = safe_get(host.rstrip("/") + "/robots.txt", timeout=8)
        return r.status_code == 200 and len(r.text) > 0
    except Exception:
        return False

def sitemap_exists(host: str, soup: BeautifulSoup) -> bool:
    # Check /sitemap.xml or link rel=sitemap
    try:
        r = safe_get(host.rstrip("/") + "/sitemap.xml", timeout=8)
        if r.status_code == 200 and len(r.content) > 0:
            return True
    except Exception:
        pass
    link = soup.find("link", rel=lambda v: v and "sitemap" in v.lower())
    return bool(link)

def lazy_images_ratio(soup: BeautifulSoup) -> float:
    imgs = soup.find_all("img")
    if not imgs:
        return 1.0
    lazy = [i for i in imgs if i.get("loading") == "lazy"]
    return len(lazy) / len(imgs)

def alt_coverage_ratio(soup: BeautifulSoup) -> float:
    imgs = soup.find_all("img")
    if not imgs:
        return 1.0
    with_alt = [i for i in imgs if i.has_attr("alt") and str(i["alt"]).strip() != ""]
    return len(with_alt) / len(imgs)

def internal_link_present(soup: BeautifulSoup, host: str) -> bool:
    host_no_scheme = host.split("://", 1)[-1]
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/") or host_no_scheme in href:
            return True
    return False

def form_labels_present(soup: BeautifulSoup) -> bool:
    inputs = soup.find_all(["input", "select", "textarea"])
    labels = soup.find_all("label")
    return len(labels) >= max(1, int(len(inputs) * 0.5))

def semantic_tags_used(soup: BeautifulSoup) -> bool:
    for tag in ["main", "nav", "header", "footer", "section", "article", "aside"]:
        if soup.find(tag):
            return True
    return False

def security_header_present(headers: Dict[str, str], name: str) -> bool:
    for k, v in headers.items():
        if k.lower() == name.lower():
            return True
    return False

def hsts_configured(headers: Dict[str, str]) -> bool:
    return security_header_present(headers, "Strict-Transport-Security")

def csp_present(headers: Dict[str, str]) -> bool:
    return security_header_present(headers, "Content-Security-Policy")

def frame_protection(headers: Dict[str, str]) -> bool:
    return (security_header_present(headers, "X-Frame-Options") or
            csp_present(headers) and "frame-ancestors" in headers.get("Content-Security-Policy", "").lower())

def x_content_type_present(headers: Dict[str, str]) -> bool:
    return security_header_present(headers, "X-Content-Type-Options")

def referrer_policy_present(headers: Dict[str, str]) -> bool:
    return security_header_present(headers, "Referrer-Policy")

# --------------------------- Core Audit Endpoint ------------------------------------
@app.post("/audit")
async def audit(req: Request):
    data = await req.json()
    url = normalize_url(data.get("url", ""))
    if not url:
        raise HTTPException(status_code=400, detail="URL required")

    try:
        resp, ttfb = measure_ttfb(url)
    except Exception:
        raise HTTPException(status_code=400, detail="Site Unreachable")

    status_ok = (200 <= resp.status_code < 300)
    content = resp.content or b""
    page_size_bytes = len(content)
    headers = resp.headers or {}
    soup = BeautifulSoup(resp.text or "", "html.parser")
    host = extract_host(url)

    # Deterministic scores per check (0-100)
    metrics: List[Dict[str, str]] = []
    total_weighted_points = 0.0
    total_possible_weight = 0.0

    def add_metric(name: str, category: str, weight: int, passed: bool, score: int):
        metrics.append({"name": name, "score": score, "category": category})

        # Weighted sum with category impact
        cat_impact = CATEGORY_IMPACT.get(category, 1.0)
        nonlocal total_weighted_points, total_possible_weight
        total_weighted_points += (score * weight * cat_impact)
        total_possible_weight += (100 * weight * cat_impact)

    # ----- Technical SEO -----
    cat = "Technical SEO"
    # HTTPS Enabled
    add_metric("HTTPS Enabled", cat, 10, url.startswith("https://"), 100 if url.startswith("https://") else 0)
    # Title
    has_title = bool(soup.title and (soup.title.string or "").strip())
    add_metric("Title Tag Present", cat, 10, has_title, 100 if has_title else 0)
    # Meta Description
    meta_desc = soup.find("meta", {"name": "description"})
    has_meta_desc = bool(meta_desc and (meta_desc.get("content") or "").strip())
    add_metric("Meta Description Present", cat, 10, has_meta_desc, 100 if has_meta_desc else 0)
    # Canonical
    canonical = soup.find("link", rel=lambda v: v and "canonical" in v.lower())
    add_metric("Canonical Tag Present", cat, 8, bool(canonical), 100 if canonical else 0)
    # Robots
    add_metric("Robots.txt Accessible", cat, 7, robots_accessible(host), 100 if robots_accessible(host) else 0)
    # Sitemap
    exists_sitemap = sitemap_exists(host, soup)
    add_metric("XML Sitemap Exists", cat, 7, exists_sitemap, 100 if exists_sitemap else 0)
    # Structured data
    ldjson = soup.find_all("script", {"type": "application/ld+json"})
    add_metric("Structured Data Markup", cat, 6, bool(ldjson), 100 if ldjson else 0)
    # Hreflang
    hreflangs = soup.find_all("link", rel=lambda v: v and "alternate" in v.lower(), hreflang=True)
    add_metric("Hreflang Implementation", cat, 5, bool(hreflangs), 100 if hreflangs else 0)
    # Server 200
    add_metric("Server Response 200 OK", cat, 10, status_ok, 100 if status_ok else 0)

    # ----- On-Page SEO -----
    cat = "On-Page SEO"
    # Single H1
    h1s = soup.find_all("h1")
    add_metric("Single H1 Tag", cat, 10, len(h1s) == 1, 100 if len(h1s) == 1 else 0)
    # H2/H3 presence
    heading_ok = bool(soup.find_all("h2") or soup.find_all("h3"))
    add_metric("Heading Structure Correct (H2/H3)", cat, 8, heading_ok, 100 if heading_ok else 0)
    # ALT coverage ≥ 90%
    alt_ratio = alt_coverage_ratio(soup)
    score_alt_90 = 100 if alt_ratio >= 0.9 else int(alt_ratio * 100)
    add_metric("Image ALT Coverage ≥ 90%", cat, 8, alt_ratio >= 0.9, score_alt_90)
    # Internal links
    internal_ok = internal_link_present(soup, host)
    add_metric("Internal Linking Present", cat, 6, internal_ok, 100 if internal_ok else 0)
    # Meta title length 50–60
    title_text = (soup.title.string.strip() if has_title else "")
    title_len_ok = text_length_optimal(title_text, 50, 60)
    add_metric("Meta Title Length Optimal", cat, 5, title_len_ok, 100 if title_len_ok else max(0, 70 - abs(len(title_text) - 55) * 3))
    # Meta description length 140–160
    desc_text = (meta_desc.get("content", "").strip() if has_meta_desc else "")
    desc_len_ok = text_length_optimal(desc_text, 140, 160)
    add_metric("Meta Description Length Optimal", cat, 5, desc_len_ok, 100 if desc_len_ok else max(0, 70 - abs(len(desc_text) - 150) * 2))

    # ----- Performance -----
    cat = "Performance"
    # TTFB < 200ms
    ttfb_score = 100 if ttfb < 200 else 80 if ttfb < 400 else 50 if ttfb < 800 else 20
    add_metric("TTFB < 200ms", cat, 10, ttfb < 200, ttfb_score)
    # Page Size < 2 MB
    size_mb = page_size_bytes / (1024 * 1024)
    size_score = 100 if size_mb < 2 else 75 if size_mb < 3 else 50 if size_mb < 5 else 20
    add_metric("Page Size < 2 MB", cat, 9, size_mb < 2, size_score)
    # Lazy-loaded images
    lazy_ratio = lazy_images_ratio(soup)
    lazy_score = int(lazy_ratio * 100)
    add_metric("Images Lazy-Loaded", cat, 8, lazy_ratio >= 0.5, lazy_score)
    # Min blocking scripts
    blocking_count = count_blocking_scripts(soup)
    block_score = 100 if blocking_count == 0 else max(10, 100 - blocking_count * 15)
    add_metric("Min Blocking Scripts", cat, 7, blocking_count == 0, block_score)
    # Compression headers
    compression_ok = is_gzip_brotli(headers)
    add_metric("Resource Compression (gzip/brotli)", cat, 7, compression_ok, 100 if compression_ok else 40)

    # ----- Accessibility -----
    cat = "Accessibility"
    # Alt text coverage
    alt_cov_score = int(alt_ratio * 100)
    add_metric("Alt Text Coverage", cat, 8, alt_ratio >= 0.9, alt_cov_score)
    # ARIA roles present
    aria_present = bool(re.search(r'role="[^"]+"', resp.text))
    add_metric("ARIA Roles Present", cat, 6, aria_present, 100 if aria_present else 50)
    # Form labels present
    labels_ok = form_labels_present(soup)
    add_metric("Form Labels Present", cat, 5, labels_ok, 100 if labels_ok else 40)
    # Semantic tags used
    semantic_ok = semantic_tags_used(soup)
    add_metric("Semantic HTML Tags Used", cat, 6, semantic_ok, 100 if semantic_ok else 50)

    # ----- Security -----
    cat = "Security"
    enforce_https = check_http_enforce_https(host)
    add_metric("HTTPS Enforced (HTTP→HTTPS)", cat, 10, enforce_https, 100 if enforce_https else 0)
    add_metric("HSTS Configured", cat, 8, hsts_configured(headers), 100 if hsts_configured(headers) else 0)
    add_metric("Content Security Policy", cat, 7, csp_present(headers), 100 if csp_present(headers) else 0)
    add_metric("X-Frame-Options/Frame-Ancestors", cat, 6, frame_protection(headers), 100 if frame_protection(headers) else 0)
    add_metric("X-Content-Type-Options", cat, 6, x_content_type_present(headers), 100 if x_content_type_present(headers) else 0)
    add_metric("Referrer-Policy", cat, 5, referrer_policy_present(headers), 100 if referrer_policy_present(headers) else 0)

    # ----- UX & Mobile -----
    cat = "User Experience & Mobile"
    viewport_ok = bool(soup.find("meta", {"name": "viewport"}))
    add_metric("Viewport Meta Present", cat, 9, viewport_ok, 100 if viewport_ok else 0)
    responsive_hints_ok = has_media_queries(soup)
    add_metric("Mobile Responsive Hints", cat, 7, responsive_hints_ok, 100 if responsive_hints_ok else 40)
    non_intrusive_score = max(20, 100 - (blocking_count * 10))
    add_metric("Non-Intrusive Scripts (count)", cat, 6, blocking_count <= 2, non_intrusive_score)

    # ----- Advanced SEO & Analytics -----
    cat = "Advanced SEO & Analytics"
    analytics_ok = has_analytics(soup)
    add_metric("Analytics Tracking Installed", cat, 9, analytics_ok, 100 if analytics_ok else 0)
    search_console_heuristic = exists_sitemap and robots_accessible(host)
    add_metric("Search Console Connected (heuristic)", cat, 7, search_console_heuristic, 100 if search_console_heuristic else 50)
    social_meta_ok = has_social_meta(soup)
    add_metric("Social Meta Tags Present", cat, 5, social_meta_ok, 100 if social_meta_ok else 0)
    sitemap_submitted_heuristic = exists_sitemap
    add_metric("Sitemap Submitted (heuristic)", cat, 6, sitemap_submitted_heuristic, 100 if sitemap_submitted_heuristic else 50)

    total_grade = round((total_weighted_points / total_possible_weight) * 100)

    summary = (
        f"FF TECH ELITE audit for {url} completed.\n\n"
        f"TTFB: {round(ttfb)} ms, Page Size: {round(size_mb, 2)} MB.\n"
        f"HTTPS: {'Enabled' if url.startswith('https://') else 'Not enabled'}, "
        f"Enforce: {'Yes' if enforce_https else 'No'}, "
        f"HSTS: {'Yes' if hsts_configured(headers) else 'No'}, "
        f"CSP: {'Yes' if csp_present(headers) else 'No'}.\n\n"
        "Strategic focus: Improve performance (reduce blocking scripts, optimize images, enable compression), "
        "harden security headers (HSTS, CSP, X-Content-Type-Options), and tighten on-page SEO (title/description lengths, "
        "single H1, internal linking). Accessibility gains via alt coverage and labels will contribute to UX and SEO quality."
    )

    return JSONResponse({"total_grade": total_grade, "summary": summary, "metrics": metrics})

# --------------------------- PDF Export Endpoint ------------------------------------
@app.post("/download")
async def download(req: Request):
    data = await req.json()
    total_grade = data.get("total_grade", 0)
    summary = data.get("summary", "")
    metrics = data.get("metrics", [])

    # Group metrics by category and compute category averages
    cat_scores: Dict[str, List[int]] = {}
    for m in metrics:
        cat_scores.setdefault(m["category"], []).append(int(m["score"]))
    cat_avgs = {cat: (sum(scores) / max(1, len(scores))) for cat, scores in cat_scores.items()}

    # Create PDF in-memory
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    def draw_title(text, y):
        c.setFont("Helvetica-Bold", 18)
        c.drawString(2 * cm, y, text)

    def draw_text(text, y, size=11):
        c.setFont("Helvetica", size)
        c.drawString(2 * cm, y, text)

    y = height - 2.5 * cm
    draw_title("FF TECH ELITE — Strategic Audit Report", y)
    y -= 1.2 * cm
    draw_text(f"Overall Health Score: {total_grade}%", y, size=12)

    y -= 1.0 * cm
    draw_title("Summary", y)
    y -= 0.8 * cm
    for line in summary.split("\n"):
        draw_text(line[:95], y)  # simple wrap
        y -= 0.6 * cm
        if y < 2 * cm:
            c.showPage(); y = height - 2.5 * cm

    # Category Averages
    y -= 0.3 * cm
    draw_title("Category Averages", y)
    y -= 0.8 * cm
    for cat, avg in sorted(cat_avgs.items(), key=lambda x: -x[1]):
        draw_text(f"{cat}: {round(avg)}%", y)
        y -= 0.6 * cm
        if y < 2 * cm:
            c.showPage(); y = height - 2.5 * cm

    # Top Issues (lowest scoring items)
    y -= 0.3 * cm
    draw_title("Top Issues", y)
    y -= 0.8 * cm
    worst = sorted(metrics, key=lambda m: m["score"])[:12]
    for m in worst:
        draw_text(f"{m['category']} — {m['name']}: {int(m['score'])}%", y)
        y -= 0.6 * cm
        if y < 2 * cm:
            c.showPage(); y = height - 2.5 * cm

    c.showPage()
    c.save()
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=FFTech_Elite_Audit.pdf"},
    )

# --------------------------- Serve Frontend -----------------------------------------
INDEX_FILE = os.environ.get("INDEX_FILE", "index.html")

@app.get("/", response_class=HTMLResponse)
def root():
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>FF TECH ELITE</h1><p>Place index.html next to app.py.</p>")

# --------------------------- Entrypoint ---------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
