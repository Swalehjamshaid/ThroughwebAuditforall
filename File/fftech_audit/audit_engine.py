
# fftech_audit/audit_engine.py
from __future__ import annotations

import io
import re
import datetime as dt
from typing import Dict, List, Any

try:
    import httpx
except Exception:
    httpx = None

# ---------------------------
# Metric catalogs (keys only)
# ---------------------------
EXECUTIVE_KEYS = [
    "overall.health_score",
    "overall.grade",
    "summary.executive_text",
    "summary.strengths",
    "summary.weaknesses",
    "summary.priority_fixes",
    "summary.severity_indicators",
    "summary.category_breakdown",
    "summary.presentation_standard",
    "summary.print_ready",
]

SITE_HEALTH_KEYS = [
    "health.score",
    "health.errors_total",
    "health.warnings_total",
    "health.notices_total",
    "health.crawled_pages",
    "health.indexed_pages",
    "health.issues_trend",
    "health.crawl_budget_efficiency",
    "health.orphan_pages_pct",
    "health.audit_completion_status",
]

CRAWL_KEYS = [
    "crawl.http_2xx",
    "crawl.http_3xx",
    "crawl.http_4xx",
    "crawl.http_5xx",
    "crawl.redirect_chains",
    "crawl.redirect_loops",
    "crawl.broken_internal_links",
    "crawl.broken_external_links",
    "crawl.robots_blocked_urls",
    "crawl.meta_robots_blocked_urls",
    "crawl.non_canonical_pages",
    "crawl.missing_canonical_tags",
    "crawl.incorrect_canonical_tags",
    "crawl.sitemap_missing_pages",
    "crawl.sitemap_not_crawled_pages",
    "crawl.hreflang_errors",
    "crawl.hreflang_conflicts",
    "crawl.pagination_issues",
    "crawl.crawl_depth_distribution",
    "crawl.duplicate_parameter_urls",
]

ONPAGE_KEYS = [
    "onpage.missing_title_tags",
    "onpage.duplicate_title_tags",
    "onpage.title_too_long",
    "onpage.title_too_short",
    "onpage.missing_meta_descriptions",
    "onpage.duplicate_meta_descriptions",
    "onpage.meta_too_long",
    "onpage.meta_too_short",
    "onpage.missing_h1",
    "onpage.multiple_h1",
    "onpage.duplicate_headings",
    "onpage.thin_content_pages",
    "onpage.duplicate_content_pages",
    "onpage.low_text_html_ratio",
    "onpage.missing_image_alt_tags",
    "onpage.duplicate_alt_tags",
    "onpage.large_uncompressed_images",
    "onpage.pages_without_indexed_content",
    "onpage.missing_structured_data",
    "onpage.structured_data_errors",
    "onpage.rich_snippet_warnings",
    "onpage.missing_open_graph_tags",
    "onpage.long_urls",
    "onpage.uppercase_urls",
    "onpage.non_seo_friendly_urls",
    "onpage.too_many_internal_links",
    "onpage.pages_without_incoming_links",
    "onpage.orphan_pages",
    "onpage.broken_anchor_links",
    "onpage.redirected_internal_links",
    "onpage.nofollow_internal_links",
    "onpage.link_depth_issues",
    "onpage.external_links_count",
    "onpage.broken_external_links",
    "onpage.anchor_text_issues",
]

PERF_KEYS = [
    "perf.lcp",
    "perf.fcp",
    "perf.cls",
    "perf.total_blocking_time",
    "perf.first_input_delay",
    "perf.speed_index",
    "perf.time_to_interactive",
    "perf.dom_content_loaded",
    "perf.total_page_size",
    "perf.requests_per_page",
    "perf.unminified_css",
    "perf.unminified_js",
    "perf.render_blocking_resources",
    "perf.excessive_dom_size",
    "perf.third_party_script_load",
    "perf.server_response_time",
    "perf.image_optimization",
    "perf.lazy_loading_issues",
    "perf.browser_caching_issues",
    "perf.missing_compression",
    "perf.resource_load_errors",
]

MOBILE_SEC_INTL_KEYS = [
    "mobile.mobile_friendly",
    "mobile.viewport_meta_tag",
    "mobile.small_font_issues",
    "mobile.tap_target_issues",
    "mobile.core_web_vitals_mobile",
    "mobile.layout_issues",
    "mobile.intrusive_interstitials",
    "mobile.navigation_issues",

    "security.https_implementation",
    "security.ssl_validity",
    "security.expired_ssl",
    "security.mixed_content",
    "security.insecure_resources",
    "security.missing_security_headers",
    "security.open_directory_listing",
    "security.login_without_https",

    "intl.missing_hreflang",
    "intl.incorrect_language_codes",
    "intl.hreflang_conflicts",
    "intl.region_targeting_issues",
    "intl.multi_domain_seo_issues",

    "backlinks.domain_authority",
    "backlinks.referring_domains",
    "backlinks.total_backlinks",
    "backlinks.toxic_backlinks",
    "backlinks.nofollow_backlinks",
    "backlinks.anchor_distribution",
    "backlinks.referring_ips",
    "backlinks.lost_new_backlinks",

    "rendering.js_rendering_issues",
    "rendering.css_blocking",
    "crawl.crawl_budget_waste",
    "amp.issues",
    "pwa.issues",
    "canonicals.conflicts",
    "subdomains.duplication",
    "pagination.conflicts",
    "urls.dynamic_issues",
    "lazyload.conflicts",
    "sitemap.presence",
    "index.noindex_issues",
    "structured_data.consistency",
    "redirect.correctness",
    "rich_media.broken",
    "social.metadata_presence",
    "trend.error_trend",
    "trend.health_trend",
    "trend.crawl_trend",
    "trend.index_trend",
    "trend.core_web_vitals_trend",
    "trend.backlink_trend",
    "trend.keyword_trend",
    "trend.historical_comparison",
    "stability.overall_index",
]

COMPETITOR_KEYS = [
    "competitor.health_score",
    "competitor.performance_comparison",
    "competitor.web_vitals_comparison",
    "competitor.seo_issues_comparison",
    "competitor.broken_links_comparison",
    "competitor.authority_score",
    "competitor.backlink_growth",
    "competitor.keyword_visibility",
    "competitor.rank_distribution",
    "competitor.content_volume",
    "competitor.speed_comparison",
    "competitor.mobile_score",
    "competitor.security_score",
    "competitor.gap_score",
    "competitor.opportunity_heatmap",
    "competitor.risk_heatmap",
    "competitor.overall_rank",
]

BROKEN_LINKS_KEYS = [
    "broken.total",
    "broken.internal",
    "broken.external",
    "broken.trend",
    "broken.pages_by_impact",
    "broken.status_code_distribution",
    "broken.page_type_distribution",
    "broken.fix_priority_score",
    "broken.seo_loss_impact",
    "broken.affected_pages",
    "broken.media_links",
    "broken.resolution_progress",
    "broken.risk_severity_index",
]

OPPORTUNITY_KEYS = [
    "opportunity.high_impact",
    "opportunity.quick_wins_score",
    "opportunity.long_term_fixes",
    "opportunity.traffic_growth_forecast",
    "opportunity.ranking_growth_forecast",
    "opportunity.conversion_impact_score",
    "opportunity.content_expansion",
    "opportunity.internal_linking",
    "opportunity.speed_improvement_potential",
    "opportunity.mobile_improvement_potential",
    "opportunity.security_improvement_potential",
    "opportunity.structured_data",
    "opportunity.crawl_optimization",
    "opportunity.backlink_opportunity_score",
    "opportunity.competitive_gap_roi",
    "opportunity.fix_roadmap_timeline",
    "opportunity.time_to_fix_estimate",
    "opportunity.cost_to_fix_estimate",
    "opportunity.roi_forecast",
    "opportunity.overall_growth_readiness",
]

ALL_KEYS: List[str] = (
    EXECUTIVE_KEYS
    + SITE_HEALTH_KEYS
    + CRAWL_KEYS
    + ONPAGE_KEYS
    + PERF_KEYS
    + MOBILE_SEC_INTL_KEYS
    + COMPETITOR_KEYS
    + BROKEN_LINKS_KEYS
    + OPPORTUNITY_KEYS
)

# ---------------------------
# Base regex (fixed: use < > not &lt; &gt;)
# ---------------------------
META_DESC_RE = re.compile(
    r"<meta\b[^>]*\bname\s*=\s*['\"]description['\"][^>]*\bcontent\s*=\s*['\"](?P<content>[^
)
TITLE_RE     = re.compile(r"<title\b[^>]*>(?P<title>.*?)</title>", re.I | re.S)
H1_RE        = re.compile(r"<h1\b[^>]*>(?P<h1>.*?)</h1>", re.I | re.S)
VIEWPORT_RE  = re.compile(r"<meta\b[^>]*\bname\s*=\s*['\"]viewport['\"][^>]*>", re.I)
CANONICAL_RE = re.compile(r"<link\b[^>]*\brel\s*=\s*['\"]canonical['\"][^>]*\bhref\s*=\s*['\"][^'\"]+['\"]", re.I)
ROBOTS_NOIDX_RE = re.compile(r"<meta\b[^>]*\bname\s*=\s*['\"]robots['\"][^>]*\bcontent\s*=\s*['\"][^'\"]*noindex[^'\"]*['\"]", re.I)
OG_TAG_RE    = re.compile(r"<meta\b[^>]*\bproperty\s*=\s*['\"]og:[^'\"]+['\"][^>]*>", re.I)
LDJSON_RE    = re.compile(r"<script\b[^>]*\btype\s*=\s*['\"]application/ld\+json['\"][^>]*>", re.I)
IMG_TAG_RE   = re.compile(r"<img\b[^>]*>", re.I)
IMG_ALT_RE   = re.compile(r"<img\b[^>]*\balt\s*=\s*['\"][^'\"]*['\"][^>]*>", re.I)
A_TAG_RE     = re.compile(r"<a\b[^>]*\bhref\s*=\s*['\"][^'\"]+['\"][^>]*>", re.I)
ABS_LINK_RE  = re.compile(r"<a\b[^>]*\bhref\s*=\s*['\"]https?://[^'\"]+['\"][^>]*>", re.I)
MIXED_HTTP_RE = re.compile(r"""(?:src|href)\s*=\s*['\"]http://[^'\"]+['\"]""", re.I)

SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*>", re.I)
CSS_LINK_RE   = re.compile(r"<link\b[^>]*\brel\s*=\s*['\"]stylesheet['\"][^>]*>", re.I)

HREFLANG_RE   = re.compile(r"<link\b[^>]*\brel\s*=\s*['\"]alternate['\"][^>]*\bhreflang\s*=\s*['\"][^'\"]+['\"][^>]*>", re.I)

# ---------------------------
# Helpers
# ---------------------------
def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(x)))

def to_pct(flag: bool) -> float:
    return 100.0 if flag else 0.0

def page_size_score(page_bytes: int) -> float:
    """Score 100 for ≤700KB; linearly drop to 0 at ≥3MB."""
    low = 700 * 1024
    high = 3 * 1024 * 1024
    if page_bytes <= low:
        return 100.0
    if page_bytes >= high:
        return 0.0
    drop = (page_bytes - low) * 100.0 / (high - low)
    return clamp(100.0 - drop)

def inverse_count_score(count: int, max_good: int, max_bad: int) -> float:
    """
    Maps a count to 0–100, where <=max_good => ~100, >=max_bad => ~0.
    """
    if count <= max_good:
        return 100.0
    if count >= max_bad:
        return 0.0
    # linear between max_good and max_bad
    frac = (count - max_good) / (max_bad - max_good)
    return clamp(100.0 * (1.0 - frac))

def weighted_average(parts: dict[str, float], weights: dict[str, float]) -> float:
    total_w = sum(weights.values())
    if total_w == 0:
        return 0.0
    s = 0.0
    for k, w in weights.items():
        s += clamp(parts.get(k, 0.0)) * w
    return clamp(s / total_w)

# ---------------------------
# Engine
# ---------------------------
def grade_from_score(score: float) -> str:
    if score >= 95: return "A+"
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "F"

class AuditEngine:
    """Flexible, API-driven engine. Single-page analysis (no crawler)."""

    def _fetch(self, url: str, timeout_s: float = 15.0) -> tuple[int, str]:
        if httpx is None:
            return 0, ""
        with httpx.Client(timeout=timeout_s, follow_redirects=True, headers={"User-Agent": "FFTechAudit/1.0"}) as client:
            r = client.get(url)
            r.raise_for_status()
            return r.status_code, r.text or ""

    def run(self, url: str) -> Dict[str, Any]:
        status, html = self._fetch(url) if url else (0, "")
        page_bytes = len(html.encode("utf-8")) if html else 0

        # Signals
        title_present     = bool(TITLE_RE.search(html))
        meta_desc_present = bool(META_DESC_RE.search(html))
        h1_present        = bool(H1_RE.search(html))
        viewport_present  = bool(VIEWPORT_RE.search(html))
        canonical_present = bool(CANONICAL_RE.search(html))
        robots_noindex    = bool(ROBOTS_NOIDX_RE.search(html))
        og_count          = len(OG_TAG_RE.findall(html))
        ldjson_present    = bool(LDJSON_RE.search(html))
        img_count         = len(IMG_TAG_RE.findall(html))
        img_alt_count     = len(IMG_ALT_RE.findall(html))
        alt_ratio         = (img_alt_count / img_count * 100.0) if img_count else 0.0
        link_count        = len(A_TAG_RE.findall(html))
        abs_link_count    = len(ABS_LINK_RE.findall(html))
        script_count      = len(SCRIPT_TAG_RE.findall(html))
        css_count         = len(CSS_LINK_RE.findall(html))
        hreflang_count    = len(HREFLANG_RE.findall(html))

        is_https          = url.lower().startswith("https://") if url else False
        mixed_content     = bool(MIXED_HTTP_RE.search(html)) if (is_https and html) else False

        # Category scores (0–100) — all variable (no fixed 50)
        onpage_score = weighted_average({
            "Title":             to_pct(title_present),
            "Meta Description":  to_pct(meta_desc_present),
            "H1":                to_pct(h1_present),
            "Structured Data":   to_pct(ldjson_present),
            "Open Graph":        clamp(og_count * 20.0, 0, 100),   # 0..5+ tags → up to 100
            "Image Alt Ratio":   clamp(alt_ratio),                 # % of images with alt
            "Canonical":         to_pct(canonical_present),
        }, {
            "Title": 0.18, "Meta Description": 0.18, "H1": 0.12,
            "Structured Data": 0.12, "Open Graph": 0.10,
            "Image Alt Ratio": 0.20, "Canonical": 0.10
        })

        security_score = weighted_average({
            "HTTPS":          to_pct(is_https),
            "Mixed Content":  100.0 - to_pct(mixed_content),  # penalize if mixed
        }, {"HTTPS": 0.6, "Mixed Content": 0.4})

        mobile_score = weighted_average({
            "Viewport": to_pct(viewport_present),
        }, {"Viewport": 1.0})

        perf_score = weighted_average({
            "Page Size":             page_size_score(page_bytes),
            "Ext Scripts (inverse)": inverse_count_score(script_count, max_good=3, max_bad=20),
            "CSS Sheets (inverse)":  inverse_count_score(css_count,    max_good=2, max_bad=15),
        }, {"Page Size": 0.6, "Ext Scripts (inverse)": 0.2, "CSS Sheets (inverse)": 0.2})

        crawl_score = weighted_average({
            "Canonical":  to_pct(canonical_present),
            "Noindex":    100.0 - to_pct(robots_noindex),  # penalize if noindex
            "Hreflang":   clamp(hreflang_count * 20.0, 0, 100),  # presence/variety
            "Links":      clamp(link_count and min(link_count, 80) / 80 * 100.0 or 0.0),
        }, {"Canonical": 0.35, "Noindex": 0.35, "Hreflang": 0.15, "Links": 0.15})

        category_scores = {
            "On-Page SEO": round(onpage_score, 1),
            "Security": round(security_score, 1),
            "Mobile": round(mobile_score, 1),
            "Performance": round(perf_score, 1),
            "Crawlability": round(crawl_score, 1),
        }

        overall = round(weighted_average(category_scores, {
            "On-Page SEO": 0.35,
            "Security":    0.20,
            "Mobile":      0.10,
            "Performance": 0.20,
            "Crawlability":0.15,
        }), 1)
        grade = grade_from_score(overall)

        # Executive panels (basic rules-based text)
        strengths, weaknesses, priority_fixes = [], [], []
        if is_https: strengths.append("HTTPS implemented")
        else:
            weaknesses.append("HTTPS missing")
            priority_fixes.append("Implement/renew SSL (HTTPS) across all pages.")
        if title_present: strengths.append("Title tag present")
        else:
            weaknesses.append("Missing title tag")
            priority_fixes.append("Add and optimize unique Title tags.")
        if meta_desc_present: strengths.append("Meta description present")
        else:
            weaknesses.append("Missing meta description")
            priority_fixes.append("Add compelling Meta descriptions (≤ 160 chars).")
        if canonical_present: strengths.append("Canonical tag present")
        else:
            weaknesses.append("Canonical tag missing")
            priority_fixes.append("Add canonical tags to prevent duplication.")
        if ldjson_present: strengths.append("Structured data detected")
        if viewport_present: strengths.append("Viewport meta for mobile detected")
        if mixed_content: weaknesses.append("Mixed content (HTTP resources on HTTPS)")

        executive_text = (
            "This audit summarizes foundational signals from the page HTML. Scores vary by Title/Meta/H1, "
            "structured data, mobile viewport, canonicalization, link/mixed-content hygiene, and page weight. "
            "For full 200-metric coverage (crawlability across the whole site, Core Web Vitals, backlinks, "
            "competitor analysis), enable crawler and performance modules."
        )

        metrics: Dict[str, Any] = {
            # A. Executive summary & grading
            "overall.health_score": overall,
            "overall.grade": grade,
            "summary.executive_text": executive_text,
            "summary.strengths": strengths,
            "summary.weaknesses": weaknesses,
            "summary.priority_fixes": priority_fixes,
            "summary.severity_indicators": {
                "MixedContent": mixed_content,
                "RobotsNoindex": robots_noindex,
            },
            "summary.category_breakdown": category_scores,
            "summary.presentation_standard": "Industry standard layout",
            "summary.print_ready": True,

            # B. Site health (single-page proxy)
            "health.score": overall,
            "health.audit_completion_status": "partial",

            # C. Crawlability (single-page proxies + placeholders)
            "crawl.missing_canonical_tags": 0 if canonical_present else 1,
            "crawl.hreflang_errors": 0 if hreflang_count >= 1 else 1,
            "crawl.hreflang_conflicts": None,
            "crawl.robots_blocked_urls": None,

            # D. On-page
            "onpage.missing_title_tags": 0 if title_present else 1,
            "onpage.missing_meta_descriptions": 0 if meta_desc_present else 1,
            "onpage.missing_h1": 0 if h1_present else 1,
            "onpage.missing_structured_data": 0 if ldjson_present else 1,
            "onpage.missing_open_graph_tags": 0 if og_count > 0 else 1,
            "onpage.external_links_count": abs_link_count,
            "onpage.missing_image_alt_tags": 0 if alt_ratio >= 60.0 else 1,  # threshold 60%
            # Placeholders for deeper checks
            **{key: None for key in ONPAGE_KEYS if key not in {
                "onpage.missing_title_tags",
                "onpage.missing_meta_descriptions",
                "onpage.missing_h1",
                "onpage.missing_structured_data",
                "onpage.missing_open_graph_tags",
                "onpage.external_links_count",
                "onpage.missing_image_alt_tags",
            }},

            # E. Performance (proxies + placeholders)
            "perf.total_page_size": page_bytes,
            "perf.requests_per_page": script_count + css_count,  # crude proxy
            "perf.render_blocking_resources": css_count,          # crude proxy
            **{key: None for key in PERF_KEYS if key not in {
                "perf.total_page_size",
                "perf.requests_per_page",
                "perf.render_blocking_resources",
            }},

            # F. Mobile/Security/Intl
            "mobile.viewport_meta_tag": viewport_present,
            "mobile.mobile_friendly": viewport_present,  # proxy
            "security.https_implementation": is_https,
            "security.mixed_content": mixed_content,
            "index.noindex_issues": robots_noindex,
            "social.metadata_presence": og_count > 0,
            **{key: None for key in MOBILE_SEC_INTL_KEYS if key not in {
                "mobile.viewport_meta_tag",
                "mobile.mobile_friendly",
                "security.https_implementation",
                "security.mixed_content",
                "index.noindex_issues",
                "social.metadata_presence",
            }},

            # G/H/I placeholders
            **{key: None for key in COMPETITOR_KEYS},
            **{key: None for key in BROKEN_LINKS_KEYS},
            **{key: None for key in OPPORTUNITY_KEYS},

            # Raw signals
            "page.bytes": page_bytes,
            "http.status": status,
            "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }

        # Rows for UI (category bars + direct signals)
        rows: List[Dict[str, Any]] = [
            {"label": "Overall Score",         "value": overall},
            {"label": "On-Page SEO",           "value": onpage_score},
            {"label": "Security (HTTPS/Mixed)","value": security_score},
            {"label": "Mobile (Viewport)",     "value": mobile_score},
            {"label": "Performance (Weight/Req)","value": perf_score},
            {"label": "Crawlability (Canon/Noindex/Hreflang/Links)","value": crawl_score},

            {"label": "Title Tag Present",            "value": to_pct(title_present)},
            {"label": "Meta Description Present",     "value": to_pct(meta_desc_present)},
            {"label": "H1 Present",                   "value": to_pct(h1_present)},
            {"label": "Structured Data Present",      "value": to_pct(ldjson_present)},
            {"label": "Open Graph Tags Present",      "value": to_pct(og_count > 0)},
            {"label": "Viewport Meta Present",        "value": to_pct(viewport_present)},
            {"label": "Canonical Present",            "value": to_pct(canonical_present)},
            {"label": "Mixed Content Detected (bad)", "value": 100.0 if mixed_content else 0.0},
            {"label": "Image Alt Coverage (%)",       "value": clamp(alt_ratio)},
        ]

        metrics["rows"] = rows
        return metrics

# ---------------------------
# PDF Report (5 pages)
# ---------------------------
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

def _draw_header(c: canvas.Canvas, title: str, url: str, page_no: int):
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2 * cm, 28 * cm, title)
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, 27.4 * cm, f"Target: {url}")
    c.drawRightString(19 * cm, 27.4 * cm, f"Page {page_no}/5")
    c.line(2 * cm, 27.2 * cm, 19 * cm, 27.2 * cm)

def _bar(c: canvas.Canvas, x: float, y: float, w: float, h: float, pct: float, label: str):
    pct = max(0.0, min(100.0, pct))
    c.setFillColor(colors.HexColor("#e9ecef"))
    c.rect(x, y, w, h, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#6f42c1"))
    c.rect(x, y, w * (pct / 100.0), h, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    c.drawString(x, y + h + 2, f"{label} – {pct:.1f}%")

def generate_pdf_report(url: str, metrics: Dict[str, Any], rows: List[Dict[str, Any]]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    # Page 1 – Executive Summary
    _draw_header(c, "FF Tech – Executive Summary", url, 1)
    grade = metrics.get("overall.grade", "-")
    score = metrics.get("overall.health_score", 0)
    c.setFont("Helvetica-Bold", 48)
    c.setFillColor(colors.HexColor("#0d6efd"))
    c.drawString(2 * cm, 23 * cm, f"Grade: {grade}")
    c.setFont("Helvetica", 14)
    c.setFillColor(colors.black)
    c.drawString(2 * cm, 21.5 * cm, f"Overall Site Health Score: {score:.1f}%")
    y = 19.5 * cm
    for row in rows[:4]:
        _bar(c, 2 * cm, y, 16 * cm, 0.6 * cm, float(row.get("value", 0.0)), str(row.get("label", "Metric")))
        y -= 1.2 * cm
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, 6 * cm, "Conclusion: Foundational signals summarized. Enable crawler/perf modules for full coverage.")
    c.showPage()

    # Page 2 – Category Breakdown
    _draw_header(c, "Category Breakdown", url, 2)
    cat = metrics.get("summary.category_breakdown") or {}
    y = 24 * cm
    for label, pct in [
        ("On-Page SEO", cat.get("On-Page SEO", 0)),
        ("Security",    cat.get("Security", 0)),
        ("Mobile",      cat.get("Mobile", 0)),
        ("Performance", cat.get("Performance", 0)),
        ("Crawlability",cat.get("Crawlability", 0)),
    ]:
        _bar(c, 2 * cm, y, 16 * cm, 0.6 * cm, float(pct or 0), label)
        y -= 1.2 * cm
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, 6 * cm, "Conclusion: Prioritize HTTPS, meta basics, canonicalization, and page weight.")
    c.showPage()

    # Page 3 – Strengths & Weaknesses
    _draw_header(c, "Strengths & Weaknesses", url, 3)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2 * cm, 25.5 * cm, "Strengths")
    c.setFont("Helvetica", 10)
    strengths = metrics.get("summary.strengths") or []
    y = 24.5 * cm
    if strengths:
        for s in strengths:
            c.drawString(2 * cm, y, f"• {s}")
            y -= 0.7 * cm
    else:
        c.drawString(2 * cm, y, "• No strong signals detected in base checks.")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2 * cm, y - 0.5 * cm, "Weak Areas")
    c.setFont("Helvetica", 10)
    weaknesses = metrics.get("summary.weaknesses") or []
    y = y - 1.2 * cm
    if weaknesses:
        for w in weaknesses:
            c.drawString(2 * cm, y, f"• {w}")
            y -= 0.7 * cm
    else:
        c.drawString(2 * cm, y, "• No immediate weaknesses detected in base checks.")
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, 6 * cm, "Conclusion: Address HTTPS/meta/canonical first; then crawler & performance.")
    c.showPage()

    # Page 4 – Priority Fixes
    _draw_header(c, "Priority Fixes & Roadmap", url, 4)
    c.setFont("Helvetica", 10)
    fixes = metrics.get("summary.priority_fixes") or [
        "Implement/renew SSL (HTTPS) across all pages.",
        "Ensure unique Title and Meta Description for every page.",
        "Add canonical tags to prevent duplication.",
        "Optimize page weight; reduce blocking CSS/JS.",
        "Add structured data; validate with Rich Results Test.",
    ]
    y = 25 * cm
    for f in fixes:
        c.drawString(2 * cm, y, f"• {f}")
        y -= 0.8 * cm
    c.drawString(2 * cm, 6 * cm, "Conclusion: Stabilize foundation, then deeper crawl/perf analysis.")
    c.showPage()

    # Page 5 – Certified Export
    _draw_header(c, "Certified Export", url, 5)
    c.setFont("Helvetica", 12)
    c.drawString(2 * cm, 25.5 * cm, "Certification")
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, 24.7 * cm, "This report is generated by FF Tech AI Website Audit SaaS.")
    c.drawString(2 * cm, 24.0 * cm, "It summarizes base signals and recommends enabling full modules for comprehensive insights.")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(2 * cm, 22.5 * cm, f"Overall Grade: {metrics.get('overall.grade', '-')}")
    c.drawString(2 * cm, 21.8 * cm, f"Overall Score: {metrics.get('overall.health_score', 0):.1f}%")
    c.setFont("Helvetica", 9)
    c.drawString(2 * cm, 6 * cm, f"Generated at: {metrics.get('generated_at', '')}")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()
``
