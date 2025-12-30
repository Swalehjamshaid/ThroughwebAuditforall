
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
# Metric Catalog (keys only)
# ---------------------------
# A. Executive Summary & Grading (1–10)
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

# B. Overall Site Health (11–20)
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

# C. Crawlability & Indexation (21–40)
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

# D. On-Page SEO (41–75)
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

# E. Performance & Technical (76–96)
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

# F. Mobile, Security & International (97–150)
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

# G. Competitor Analysis (151–167)
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

# H. Broken Links Intelligence (168–180)
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

# I. Opportunities, Growth & ROI (181–200)
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
# Base checks (regex)
# ---------------------------
META_DESC_RE = re.compile(
    r"<meta\b[^>]*\bname\s*=\s*['\"]description['\"][^>]*\bcontent\s*=\s*'\"['\"]",
    re.I,
)
TITLE_RE = re.compile(r"<title\b[^>]*>(?P<title>.*?)</title>", re.I | re.S)

# ---------------------------
# Scoring
# ---------------------------
def grade_from_score(score: float) -> str:
    if score >= 95: return "A+"
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "F"

class AuditEngine:
    """Flexible, API-driven engine. Frontend-agnostic."""

    def _fetch(self, url: str, timeout_s: float = 15.0) -> tuple[int, str]:
        """Return (status_code, html). Uses httpx if available."""
        if httpx is None:
            return 0, ""
        with httpx.Client(timeout=timeout_s, follow_redirects=True, headers={"User-Agent": "FFTechAudit/1.0"}) as client:
            r = client.get(url)
            r.raise_for_status()
            return r.status_code, r.text or ""

    def run(self, url: str) -> Dict[str, Any]:
        """Run audit and return metrics dict with 'rows' for UI and scoring."""
        status, html = self._fetch(url) if url else (0, "")
        page_bytes = len(html.encode("utf-8")) if html else 0

        has_desc = bool(META_DESC_RE.search(html))
        has_title = bool(TITLE_RE.search(html))
        is_https = url.lower().startswith("https://") if url else False

        score = 0.0
        score += 35.0 if has_desc else 0.0
        score += 25.0 if has_title else 0.0
        score += 10.0 if is_https else 0.0
        score += min(page_bytes / 1024.0, 30.0)
        score = max(0.0, min(100.0, score))
        grade = grade_from_score(score)

        metrics: Dict[str, Any] = {
            "overall.health_score": round(score, 2),
            "overall.grade": grade,
            "summary.executive_text": None,
            "summary.strengths": None,
            "summary.weaknesses": None,
            "summary.priority_fixes": None,
            "summary.severity_indicators": None,
            "summary.category_breakdown": None,
            "summary.presentation_standard": "Industry standard layout",
            "summary.print_ready": True,

            "health.score": round(score, 2),
            "health.errors_total": None,
            "health.warnings_total": None,
            "health.notices_total": None,
            "health.crawled_pages": None,
            "health.indexed_pages": None,
            "health.issues_trend": None,
            "health.crawl_budget_efficiency": None,
            "health.orphan_pages_pct": None,
            "health.audit_completion_status": "partial",

            **{key: None for key in CRAWL_KEYS},

            "onpage.missing_title_tags": 0 if has_title else 1,
            "onpage.missing_meta_descriptions": 0 if has_desc else 1,
            **{key: None for key in ONPAGE_KEYS if key not in {"onpage.missing_title_tags", "onpage.missing_meta_descriptions"}},

            **{key: None for key in PERF_KEYS},

            "security.https_implementation": is_https,
            **{key: None for key in MOBILE_SEC_INTL_KEYS if key != "security.https_implementation"},

            **{key: None for key in COMPETITOR_KEYS},
            **{key: None for key in BROKEN_LINKS_KEYS},
            **{key: None for key in OPPORTUNITY_KEYS},

            "page.bytes": page_bytes,
            "http.status": status,
            "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }

        rows: List[Dict[str, Any]] = [
            {"label": "Meta Description", "value": 100.0 if has_desc else 0.0},
            {"label": "Title Tag", "value": 100.0 if has_title else 0.0},
            {"label": "HTTPS Enabled", "value": 100.0 if is_https else 0.0},
            {"label": "Page Size (normalized)", "value": min(page_bytes / (1024.0 * 2.0) * 100.0, 100.0)},
            {"label": "Overall Score", "value": score},
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
    c.drawString(2 * cm, 21.5 * cm, f"Overall Site Health Score: {score:.2f}%")
    y = 19.5 * cm
    for row in rows[:4]:
        _bar(c, 2 * cm, y, 16 * cm, 0.6 * cm, float(row.get("value", 0.0)), str(row.get("label", "Metric")))
        y -= 1.2 * cm
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, 6 * cm, "Conclusion: Your website shows the above signals. See subsequent pages for category breakdown and priorities.")
    c.showPage()

    # Page 2 – Category Scores (placeholders)
    _draw_header(c, "Category Breakdown", url, 2)
    categories = [
        ("Site Health", metrics.get("health.score", 0)),
        ("On-Page", 50 if metrics.get("onpage.missing_title_tags") == 0 and metrics.get("onpage.missing_meta_descriptions") == 0 else 20),
        ("Crawlability", 0),
        ("Performance", 0),
        ("Mobile/Security", 100 if metrics.get("security.https_implementation") else 20),
    ]
    y = 24 * cm
    for label, pct in categories:
        _bar(c, 2 * cm, y, 16 * cm, 0.6 * cm, float(pct or 0), label)
        y -= 1.2 * cm
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, 6 * cm, "Conclusion: Prioritize HTTPS, on-page completeness, and full crawl/performance assessments.")
    c.showPage()

    # Page 3 – Strengths & Weaknesses
    _draw_header(c, "Strengths & Weaknesses", url, 3)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2 * cm, 25.5 * cm, "Strengths")
    c.setFont("Helvetica", 10)
    strengths = []
    if metrics.get("security.https_implementation"):
        strengths.append("HTTPS implemented")
    if metrics.get("onpage.missing_title_tags") == 0:
        strengths.append("Title tag present")
    if metrics.get("meta.description.present") or metrics.get("onpage.missing_meta_descriptions") == 0:
        strengths.append("Meta description present")
    if not strengths:
        strengths = ["No strong signals detected in base checks."]
    y = 24.5 * cm
    for s in strengths:
        c.drawString(2 * cm, y, f"• {s}")
        y -= 0.7 * cm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(2 * cm, y - 0.5 * cm, "Weak Areas")
    c.setFont("Helvetica", 10)
    weaknesses = []
    if not metrics.get("security.https_implementation"):
        weaknesses.append("HTTPS missing")
    if metrics.get("onpage.missing_title_tags") == 1:
        weaknesses.append("Missing title tag")
    if metrics.get("onpage.missing_meta_descriptions") == 1:
        weaknesses.append("Missing meta description")
    if not weaknesses:
        weaknesses = ["No immediate weaknesses detected in base checks."]
    y = y - 1.2 * cm
    for w in weaknesses:
        c.drawString(2 * cm, y, f"• {w}")
        y -= 0.7 * cm

    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, 6 * cm, "Conclusion: Address missing HTTPS and meta elements first, then proceed to full crawl and performance audit.")
    c.showPage()

    # Page 4 – Priority Fixes & Roadmap
    _draw_header(c, "Priority Fixes & Roadmap", url, 4)
    c.setFont("Helvetica", 10)
    fixes = [
        "Implement/renew SSL (HTTPS) across all pages.",
        "Ensure every page has a unique Title and Meta Description.",
        "Run a full crawl to identify broken links, redirects, and canonical issues.",
        "Measure Core Web Vitals using lab + field data.",
        "Optimize images and enable compression/caching.",
    ]
    y = 25 * cm
    for f in fixes:
        c.drawString(2 * cm, y, f"• {f}")
        y -= 0.8 * cm
    c.drawString(2 * cm, 6 * cm, "Conclusion: Prioritize foundational SEO signals, then performance and crawl hygiene for stable gains.")
    c.showPage()

    # Page 5 – Certified Export
    _draw_header(c, "Certified Export", url, 5)
    c.setFont("Helvetica", 12)
    c.drawString(2 * cm, 25.5 * cm, "Certification")
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, 24.7 * cm, "This report is generated by FF Tech AI Website Audit SaaS.")
    c.drawString(2 * cm, 24.0 * cm, "It summarizes signals from a base fetch and recommends a full audit for comprehensive insights.")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(2 * cm, 22.5 * cm, f"Overall Grade: {metrics.get('overall.grade', '-')}")
    c.drawString(2 * cm, 21.8 * cm, f"Overall Score: {metrics.get('overall.health_score', 0):.2f}%")
    c.setFont("Helvetica", 9)
    c.drawString(2 * cm, 6 * cm, f"Generated at: {metrics.get('generated_at', '')}")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()
