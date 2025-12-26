
# app.py
import os
import io
from datetime import datetime
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Optional: Pillow for fallback favicon generation
try:
    from PIL import Image, ImageDraw
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Mount /static if present
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Simple in-memory store for previous scores
PREVIOUS_AUDITS: dict[str, dict] = {}


# ----------------- Helpers -----------------

def normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return raw
    parsed = urlparse(raw)
    if not parsed.scheme:
        raw = "https://" + raw
    return raw

def safe_request(url: str, method: str = "GET", **kwargs) -> requests.Response | None:
    try:
        kwargs.setdefault("timeout", (6, 12))  # connect, read
        kwargs.setdefault("allow_redirects", True)
        kwargs.setdefault("headers", {
            "User-Agent": "FFTech-AuditBot/1.0 (+https://fftech.example)"
        })
        return requests.request(method.upper(), url, **kwargs)
    except Exception:
        return None

def grade_from_score(score: int) -> str:
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    if score >= 50: return "E"
    return "F"

def pct(n: int, d: int) -> float:
    return (n / d * 100.0) if d else 0.0

def detect_mixed_content(soup: BeautifulSoup, page_scheme: str) -> bool:
    if page_scheme != "https":
        return False
    for tag in soup.find_all(["img", "script", "link", "iframe", "video", "audio", "source"]):
        for attr in ["src", "href", "data", "poster"]:
            val = tag.get(attr)
            if isinstance(val, str) and val.startswith("http://"):
                return True
    return False

def _default_recommendations() -> dict:
    return {
        "total_errors": "Fix errors first; they block indexing or break UX.",
        "total_warnings": "Address warnings next; they impact performance and ranking.",
        "total_notices": "Optional improvements for incremental gains.",
        "performance_score": "Optimize images, enable compression, reduce render‑blocking scripts, and cache aggressively.",
        "seo_score": "Ensure unique titles, meta descriptions, H1, canonical tags, and structured data.",
        "accessibility_score": "Provide alt text, set language attribute, and use proper landmarks/labels.",
        "best_practices_score": "Prefer HTTPS, avoid mixed content, and use modern resource patterns.",
        "security_score": "Add HSTS, CSP, XFO, XCTO, and Referrer/Permissions policies.",
        "pages_crawled": "Expand coverage via sitemaps and internal linking.",
        "largest_contentful_paint_ms": "Inline critical CSS; preconnect; optimize hero assets.",
        "first_input_delay_ms": "Defer heavy JS; split bundles; reduce main-thread tasks.",
        "core_web_vitals_pass_rate_%": "Focus on LCP/CLS/INP; measure with RUM and lab tools.",
    }

def generate_favicon_bytes() -> bytes:
    if PIL_AVAILABLE:
        img = Image.new("RGBA", (32, 32), (99, 102, 241, 255))  # Indigo
        draw = ImageDraw.Draw(img)
        draw.ellipse((6, 6, 26, 26), outline=(255, 255, 255, 220), width=2)
        buf = io.BytesIO()
        img.save(buf, format="ICO")
        buf.seek(0)
        return buf.getvalue()
    return b"\x00\x00\x01\x00\x01\x00\x10\x10\x00\x00\x01\x00\x04\x00(\x01\x00\x00\x16\x00\x00\x00" + b"\x00" * 64


# ----------------- Core Audit Logic -----------------

def audit_website(url: str) -> dict:
    """Fetch homepage, parse HTML & headers, compute heuristic scores and issues."""
    url = normalize_url(url)
    resp = safe_request(url, "GET")
    errors: list[dict] = []
    warnings: list[dict] = []
    notices: list[dict] = []

    status_code = resp.status_code if resp else None
    final_url = resp.url if resp else url
    headers = dict(resp.headers) if resp else {}
    elapsed_ms = int(resp.elapsed.total_seconds() * 1000) if resp else 0
    html = resp.text if (resp and resp.text) else ""
    page_size_bytes = len(resp.content) if resp else 0
    page_scheme = urlparse(final_url).scheme or "https"

    # On failure, return minimal audit
    if not resp or (status_code and status_code >= 400):
        errors.append({
            "name": "Site unreachable or error status",
            "severity": "high",
            "suggestion": "Verify DNS, TLS certificate, and that the server responds with 2xx for the homepage."
        })
        site_health_score = 0
        audit = {
            "website": {"url": url},
            "site_health_score": site_health_score,
            "grade": grade_from_score(site_health_score),
            "competitors": [],
            "top_issues": errors,
            "metrics_summary": {
                "total_errors": len(errors),
                "total_warnings": 0,
                "total_notices": 0,
                "performance_score": 0,
                "seo_score": 0,
                "accessibility_score": 0,
                "best_practices_score": 0,
                "security_score": 0,
                "pages_crawled": 1,
                "largest_contentful_paint_ms": 0,
                "first_input_delay_ms": 0,
                "core_web_vitals_pass_rate_%": 0,
            },
            "recommendations": _default_recommendations(),
            "weaknesses": [e["name"] for e in errors],
            "finished_at": datetime.now().strftime("%b %d, %Y %H:%M"),
        }
        previous_audit = PREVIOUS_AUDITS.get(url)
        PREVIOUS_AUDITS[url] = {"site_health_score": site_health_score, "timestamp": audit["finished_at"]}
        return {"audit": audit, "previous_audit": previous_audit}

    # Parse HTML
    soup = BeautifulSoup(html, "html.parser")

    # --------- SEO ---------
    title_tag = soup.title.string.strip() if soup.title and soup.title.string else ""
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_desc = (meta_desc_tag.get("content") or "").strip() if meta_desc_tag else ""
    h1_tags = soup.find_all("h1")
    h1_count = len(h1_tags)
    canonical_link = soup.find("link", rel=lambda v: v and "canonical" in v.lower())
    lang_attr = soup.html.get("lang") if soup.html else None
    robots_meta_tag = soup.find("meta", attrs={"name": "robots"})
    robots_meta = (robots_meta_tag.get("content") or "").lower().strip() if robots_meta_tag else ""

    a_tags = soup.find_all("a")
    total_links = len(a_tags)
    parsed_netloc = urlparse(final_url).netloc
    internal_links = 0
    external_links = 0
    for a in a_tags:
        href = a.get("href") or ""
        abs_url = urljoin(final_url, href)
        netloc = urlparse(abs_url).netloc
        if not href:
            continue
        if href.startswith("#"):
            internal_links += 1
        elif netloc == parsed_netloc:
            internal_links += 1
        else:
            external_links += 1

    img_tags = soup.find_all("img")
    total_imgs = len(img_tags)
    imgs_without_alt = len([i for i in img_tags if not (i.get("alt") and i.get("alt").strip())])

    ld_json_count = len(soup.find_all("script", attrs={"type": "application/ld+json"}))
    hreflang_count = len(soup.find_all("link", attrs={"rel": "alternate", "hreflang": True}))
    viewport_tag = soup.find("meta", attrs={"name": "viewport"})
    favicon_link = soup.find("link", rel=lambda v: v and ("icon" in v.lower() or "shortcut icon" in v.lower()))

    # --------- Performance (heuristics) ---------
    script_tags = soup.find_all("script")
    link_stylesheets = soup.find_all("link", rel=lambda v: v and "stylesheet" in v.lower())

    def is_blocking_script(tag) -> bool:
        if tag.name != "script":
            return False
        if tag.get("type") == "module":
            return False
        return not (bool(tag.get("async")) or bool(tag.get("defer")))

    blocking_script_count = sum(1 for s in script_tags if is_blocking_script(s))
    stylesheet_count = len(link_stylesheets)

    size_mb = (page_size_bytes / 1024.0 / 1024.0)
    ttfb_ms = elapsed_ms

    # --------- Security headers ---------
    hsts = headers.get("Strict-Transport-Security")
    csp = headers.get("Content-Security-Policy")
    xfo = headers.get("X-Frame-Options")
    xcto = headers.get("X-Content-Type-Options")
    refpol = headers.get("Referrer-Policy")
    perm_pol = headers.get("Permissions-Policy")
    mixed_content = detect_mixed_content(soup, page_scheme)

    # --------- robots/sitemap ---------
    origin = f"{urlparse(final_url).scheme}://{urlparse(final_url).netloc}"
    robots_resp = safe_request(urljoin(origin, "/robots.txt"), "HEAD")
    sitemap_resp = safe_request(urljoin(origin, "/sitemap.xml"), "HEAD")
    has_robots = bool(robots_resp and robots_resp.status_code < 400)
    has_sitemap = bool(sitemap_resp and sitemap_resp.status_code < 400)

    # --------- Build issues ---------
    if not title_tag:
        errors.append({"name": "Missing <title>", "severity": "high",
                       "suggestion": "Add a concise, descriptive title (50–60 chars) including primary keyword."})
    elif len(title_tag) < 10 or len(title_tag) > 65:
        warnings.append({"name": "Suboptimal title length", "severity": "medium",
                         "suggestion": "Aim for ~50–60 characters to avoid truncation and ensure clarity."})

    if not meta_desc:
        warnings.append({"name": "Missing meta description", "severity": "medium",
                         "suggestion": "Add a compelling description (120–160 chars) with key phrases."})
    elif len(meta_desc) < 50 or len(meta_desc) > 170:
        notices.append({"name": "Meta description length outside ideal range", "severity": "low",
                        "suggestion": "Keep descriptions between ~120–160 characters."})

    if h1_count != 1:
        warnings.append({"name": f"H1 count is {h1_count}", "severity": "medium",
                         "suggestion": "Use exactly one H1 per page, reflecting the main topic."})

    if not canonical_link:
        notices.append({"name": "Missing canonical link", "severity": "low",
                        "suggestion": "Add <link rel='canonical'> to avoid duplicate content issues."})

    if imgs_without_alt > 0:
        ratio = pct(imgs_without_alt, total_imgs)
        sev = "medium" if ratio > 20 else "low"
        (warnings if sev == "medium" else notices).append({
            "name": f"{imgs_without_alt} images without alt",
            "severity": sev,
            "suggestion": "Provide descriptive alt text for accessibility and SEO."
        })

    if ld_json_count == 0:
        notices.append({"name": "No structured data (JSON-LD)", "severity": "low",
                        "suggestion": "Add JSON‑LD (e.g., Organization, Breadcrumb, Product) on key pages."})

    if not lang_attr:
        warnings.append({"name": "Missing <html lang> attribute", "severity": "medium",
                         "suggestion": "Set <html lang='en'> (or appropriate) for accessibility/SEO."})

    if "noindex" in robots_meta:
        warnings.append({"name": "robots meta includes noindex", "severity": "medium",
                         "suggestion": "Ensure indexable pages don’t include noindex."})

    # Performance
    if size_mb > 2.0:
        errors.append({"name": f"Large page payload (~{size_mb:.2f} MB)", "severity": "high",
                       "suggestion": "Compress images (WebP/AVIF), minify assets, and lazy-load non-critical content."})
    elif size_mb > 1.0:
        warnings.append({"name": f"Page size is heavy (~{size_mb:.2f} MB)", "severity": "medium",
                         "suggestion": "Optimize media, bundle/minify CSS/JS, enable server-side compression."})

    if ttfb_ms > 1500:
        errors.append({"name": f"Slow TTFB (~{ttfb_ms} ms)", "severity": "high",
                       "suggestion": "Use CDN/edge caching, optimize origin, enable HTTP/2/3."})
    elif ttfb_ms > 800:
        warnings.append({"name": f"Elevated TTFB (~{ttfb_ms} ms)", "severity": "medium",
                         "suggestion": "Improve caching and server performance; preconnect to critical origins."})

    if blocking_script_count > 3:
        warnings.append({"name": f"Many render‑blocking scripts ({blocking_script_count})", "severity": "medium",
                         "suggestion": "Defer/async non-critical JS; split bundles; consider type='module'."})
    elif blocking_script_count > 0:
        notices.append({"name": f"Some blocking scripts ({blocking_script_count})", "severity": "low",
                        "suggestion": "Add async/defer to reduce main-thread blocking."})

    if stylesheet_count > 4:
        notices.append({"name": f"Many stylesheets ({stylesheet_count})", "severity": "low",
                        "suggestion": "Bundle/minify CSS; inline critical CSS; defer non-critical."})

    # Security
    if page_scheme != "https":
        errors.append({"name": "Page served over HTTP", "severity": "high",
                       "suggestion": "Redirect to HTTPS and issue a valid TLS certificate."})
    if not hsts:
        warnings.append({"name": "Missing HSTS", "severity": "medium",
                         "suggestion": "Add Strict-Transport-Security to enforce HTTPS."})
    if not csp:
        warnings.append({"name": "Missing CSP", "severity": "medium",
                         "suggestion": "Add Content-Security-Policy to restrict sources and mitigate XSS."})
    if not xfo:
        notices.append({"name": "Missing X-Frame-Options", "severity": "low",
                        "suggestion": "Add X-Frame-Options: SAMEORIGIN (or CSP frame-ancestors)."})
    if not xcto:
        notices.append({"name": "Missing X-Content-Type-Options", "severity": "low",
                        "suggestion": "Add X-Content-Type-Options: nosniff."})
    if not refpol:
        notices.append({"name": "Missing Referrer-Policy", "severity": "low",
                        "suggestion": "Add a Referrer-Policy (e.g., no-referrer or strict forms)."})
    if not perm_pol:
        notices.append({"name": "Missing Permissions-Policy", "severity": "low",
                        "suggestion": "Declare Permissions-Policy for powerful features."})
    if mixed_content:
        errors.append({"name": "Mixed content detected", "severity": "high",
                       "suggestion": "Ensure all resources load via HTTPS; update hardcoded http:// links."})

    # Discoverability
    if not has_robots:
        notices.append({"name": "robots.txt not found", "severity": "low",
                        "suggestion": "Add robots.txt to control crawl behavior."})
    if not has_sitemap:
        notices.append({"name": "sitemap.xml not found", "severity": "low",
                        "suggestion": "Generate a sitemap and reference it in robots.txt."})

    # --------- Scores (heuristics) ---------
    seo_score = 100
    perf_score = 100
    a11y_score = 100
    bp_score = 100
    sec_score = 100

    # SEO penalties
    if not title_tag: seo_score -= 20
    if title_tag and (len(title_tag) < 10 or len(title_tag) > 65): seo_score -= 5
    if not meta_desc: seo_score -= 15
    if meta_desc and (len(meta_desc) < 50 or len(meta_desc) > 170): seo_score -= 5
    if h1_count != 1: seo_score -= 10
    if not canonical_link: seo_score -= 5
    if imgs_without_alt > 0 and pct(imgs_without_alt, total_imgs) > 20: seo_score -= 10
    if ld_json_count == 0: seo_score -= 5

    # Performance penalties
    if size_mb > 2.0: perf_score -= 30
    elif size_mb > 1.0: perf_score -= 15
    if ttfb_ms > 1500: perf_score -= 30
    elif ttfb_ms > 800: perf_score -= 15
    if blocking_script_count > 3: perf_score -= 20
    elif blocking_script_count > 0: perf_score -= 10
    if stylesheet_count > 4: perf_score -= 5

    # Accessibility penalties
    if not lang_attr: a11y_score -= 10
    if imgs_without_alt > 0:
        alt_ratio = pct(imgs_without_alt, total_imgs)
        if alt_ratio > 30: a11y_score -= 20
        elif alt_ratio > 10: a11y_score -= 10
        else: a11y_score -= 5

    # Best practices penalties
    if page_scheme != "https": bp_score -= 30
    if mixed_content: bp_score -= 10
    if any((s.get("type") == "text/javascript") for s in script_tags): bp_score -= 2

    # Security penalties
    if not hsts: sec_score -= 20
    if not csp: sec_score -= 15
    if not xfo: sec_score -= 10
    if not xcto: sec_score -= 10
    if not refpol: sec_score -= 5
    if not perm_pol: sec_score -= 5
    if mixed_content: sec_score -= 20

    site_health_score = round(
        0.28 * seo_score +
        0.26 * perf_score +
        0.18 * a11y_score +
        0.12 * bp_score +
        0.16 * sec_score
    )

    # CWV placeholders based on proxies
    largest_contentful_paint_ms = min(6000, int(1500 + size_mb * 1200 + blocking_script_count * 250))
    first_input_delay_ms = min(500, int(20 + blocking_script_count * 30))
    pass_rate = max(0, min(100, int(100 - (size_mb * 20 + blocking_script_count * 8 + (ttfb_ms / 100)))))

    # Top issues (limit 10; high -> medium -> low)
    severity_order = {"high": 0, "medium": 1, "low": 2}
    top_issues = []
    for i in errors:
        i["severity"] = "high"
        top_issues.append(i)
    for i in warnings:
        i["severity"] = "medium"
        top_issues.append(i)
    for i in notices:
        i["severity"] = "low"
        top_issues.append(i)
    top_issues.sort(key=lambda i: severity_order.get(i["severity"], 2))
    top_issues = top_issues[:10]

    metrics_summary = {
        "total_errors": len(errors),
        "total_warnings": len(warnings),
        "total_notices": len(notices),
        "performance_score": max(0, perf_score),
        "seo_score": max(0, seo_score),
        "accessibility_score": max(0, a11y_score),
        "best_practices_score": max(0, bp_score),
        "security_score": max(0, sec_score),
        "pages_crawled": 1,
        "largest_contentful_paint_ms": largest_contentful_paint_ms,
        "first_input_delay_ms": first_input_delay_ms,
        "core_web_vitals_pass_rate_%": pass_rate,
    }

    weaknesses = [i["name"] for i in errors] + [
        i["name"] for i in warnings if ("TTFB" in i["name"] or "render" in i["name"].lower())
    ]

    audit = {
        "website": {"url": final_url},
        "site_health_score": site_health_score,
        "grade": grade_from_score(site_health_score),
        "competitors": [],  # Ready for future population
        "top_issues": top_issues,
        "metrics_summary": metrics_summary,
        "recommendations": _default_recommendations(),
        "weaknesses": weaknesses,
        "finished_at": datetime.now().strftime("%b %d, %Y %H:%M"),
    }

    previous_audit = PREVIOUS_AUDITS.get(url)
    PREVIOUS_AUDITS[url] = {"site_health_score": site_health_score, "timestamp": audit["finished_at"]}
    return {"audit": audit, "previous_audit": previous_audit}


# ----------------- Routes -----------------

@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})

@app.get("/", response_class=HTMLResponse)
def home(request: Request, url: str | None = None) -> HTMLResponse:
    """
    Server-side render your provided template with audit data.
    Use /?url=https://example.com to audit a specific site.
    """
    target_url = url or "https://example.com"
    data = audit_website(target_url)
    context = {"request": request, **data}
    return templates.TemplateResponse("index.html", context)

@app.get("/api/audit")
def api_audit(url: str) -> JSONResponse:
    """
    JSON audit endpoint for client-side use (optional).
    """
    data = audit_website(url)
    return JSONResponse(data)

@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    static_path = os.path.join("static", "favicon.ico")
    if os.path.isfile(static_path):
        with open(static_path, "rb") as f:
            return Response(content=f.read(), media_type="image/x-icon")
    return Response(content=generate_favicon_bytes(), media_type="image/x-icon")
