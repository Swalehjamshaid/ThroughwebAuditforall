# fftech_audit/audit_engine.py
from __future__ import annotations
import io
import re
import datetime as dt
from typing import Dict, List, Any

try:
    import httpx
except ImportError:
    httpx = None

# ---------------------------
# Metric catalogs (keys only – unchanged, preserved for app compatibility)
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
# Regex patterns (cleaned, robust, and clearly named)
# ---------------------------
META_DESC_RE = re.compile(
    r'<meta\b[^>]*\bname\s*=\s*[\'"]description[\'"][^>]*\bcontent\s*=\s*[\'"]',
    re.IGNORECASE,
)
TITLE_RE = re.compile(r'<title\b[^>]*>(?P<title>.*?)</title>', re.IGNORECASE | re.DOTALL)
H1_RE = re.compile(r'<h1\b[^>]*>(?P<h1>.*?)</h1>', re.IGNORECASE | re.DOTALL)
VIEWPORT_RE = re.compile(
    r'<meta\b[^>]*\bname\s*=\s*[\'"]viewport[\'"][^>]*>', re.IGNORECASE
)
CANONICAL_RE = re.compile(
    r'<link\b[^>]*\brel\s*=\s*[\'"]canonical[\'"][^>]*\bhref\s*=\s*[\'"][^\'"]+[\'"]',
    re.IGNORECASE,
)
ROBOTS_NOIDX_RE = re.compile(
    r'<meta\b[^>]*\bname\s*=\s*[\'"]robots[\'"][^>]*\bcontent\s*=\s*[\'"][^\'"]*noindex[^\'"]*[\'"]',
    re.IGNORECASE,
)
OG_TAG_RE = re.compile(
    r'<meta\b[^>]*\bproperty\s*=\s*[\'"]og:[^\'"]+[\'"][^>]*>', re.IGNORECASE
)
LDJSON_RE = re.compile(
    r'<script\b[^>]*\btype\s*=\s*[\'"]application/ld\+json[\'"][^>]*>', re.IGNORECASE
)
IMG_TAG_RE = re.compile(r'<img\b[^>]*>', re.IGNORECASE)
IMG_ALT_RE = re.compile(r'<img\b[^>]*\balt\s*=\s*[\'"][^\'"]*[\'"]', re.IGNORECASE)
A_TAG_RE = re.compile(r'<a\b[^>]*\bhref\s*=\s*[\'"][^\'"]+[\'"]', re.IGNORECASE)
ABS_LINK_RE = re.compile(
    r'<a\b[^>]*\bhref\s*=\s*[\'"]https?://[^\'"]+[\'"]', re.IGNORECASE
)
MIXED_HTTP_RE = re.compile(
    r'(?:src|href)\s*=\s*[\'"]http://[^\'"]+[\'"]', re.IGNORECASE
)
SCRIPT_TAG_RE = re.compile(r'<script\b[^>]*>', re.IGNORECASE)
CSS_LINK_RE = re.compile(
    r'<link\b[^>]*\brel\s*=\s*[\'"]stylesheet[\'"][^>]*>', re.IGNORECASE
)
HREFLANG_RE = re.compile(
    r'<link\b[^>]*\brel\s*=\s*[\'"]alternate[\'"][^>]*\bhreflang\s*=\s*[\'"][^\'"]+[\'"]',
    re.IGNORECASE,
)

# ---------------------------
# Helper functions
# ---------------------------
def clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    """Clamp value between minimum and maximum."""
    return max(minimum, min(maximum, float(value)))


def to_pct(flag: bool) -> float:
    """Convert boolean to percentage score."""
    return 100.0 if flag else 0.0


def page_size_score(page_bytes: int) -> float:
    """Score page size: 100 for ≤700KB, linear drop to 0 at ≥3MB."""
    low_threshold = 700 * 1024
    high_threshold = 3 * 1024 * 1024
    if page_bytes <= low_threshold:
        return 100.0
    if page_bytes >= high_threshold:
        return 0.0
    drop = (page_bytes - low_threshold) * 100.0 / (high_threshold - low_threshold)
    return clamp(100.0 - drop)


def inverse_count_score(count: int, max_good: int, max_bad: int) -> float:
    """Inverse scoring: high count = low score."""
    count = max(0, count)
    if count <= max_good:
        return 100.0
    if count >= max_bad:
        return 0.0
    fraction = (count - max_good) / (max_bad - max_good)
    return clamp(100.0 * (1.0 - fraction))


def weighted_average(
    values: Dict[str, float], weights: Dict[str, float]
) -> float:
    """Compute weighted average with clamping."""
    total_weight = sum(weights.values())
    if total_weight == 0:
        return 0.0
    weighted_sum = sum(clamp(values.get(k, 0.0)) * w for k, w in weights.items())
    return clamp(weighted_sum / total_weight)


# ---------------------------
# Scoring utilities
# ---------------------------
def grade_from_score(score: float) -> str:
    """Convert numeric score to letter grade."""
    if score >= 95:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


# ---------------------------
# Audit Engine
# ---------------------------
class AuditEngine:
    """
    Lightweight, single-page SEO audit engine (no crawling).
    Produces metrics dictionary compatible with existing app UI and PDF generator.
    Handles empty state beautifully.
    """

    def _fetch(self, url: str, timeout_s: float = 15.0) -> tuple[int, str]:
        if httpx is None or not url:
            return 0, ""

        try:
            with httpx.Client(
                timeout=timeout_s,
                follow_redirects=True,
                headers={"User-Agent": "FFTechAudit/1.0 (+https://fftech.ai)"},
            ) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.status_code, response.text or ""
        except httpx.RequestError:
            return 0, ""

    def run(self, url: str = "") -> Dict[str, Any]:
        status, html = self._fetch(url)
        analyzed = bool(html and status == 200)
        page_bytes = len(html.encode("utf-8")) if html else 0

        # Beautiful empty state when no URL or fetch failed
        if not analyzed:
            executive_text = (
                "👋 Welcome to FF Tech AI Website Audit!\n\n"
                "Enter a website URL to instantly analyze its SEO health, performance, security, "
                "mobile-friendliness, and crawlability.\n\n"
                "You'll receive a beautiful, professional report with:\n"
                "• Overall Health Score & Grade\n"
                "• Category Breakdown\n"
                "• Strengths & Opportunities\n"
                "• Priority Fixes Roadmap\n"
                "• Print-ready PDF Export\n\n"
                "Start auditing now — get actionable insights in seconds."
            )
            strengths = [
                "Ready to analyze any website",
                "Professional PDF reports",
                "Instant foundational SEO checks",
            ]
            weaknesses = []
            priority_fixes = [
                "Enter a valid URL (e.g., https://example.com) to begin your audit."
            ]
            category_scores = {
                "On-Page SEO": None,
                "Security": None,
                "Mobile": None,
                "Performance": None,
                "Crawlability": None,
            }
            overall_score = None
            grade = "—"
            rows = [
                {"label": "Overall Score", "value": None},
                {"label": "On-Page SEO", "value": None},
                {"label": "Security", "value": None},
                {"label": "Mobile", "value": None},
                {"label": "Performance", "value": None},
                {"label": "Crawlability", "value": None},
            ]
            mixed_content = False
            robots_noindex = False
            canonical_present = False
            hreflang_count = 0
            title_present = False
            meta_desc_present = False
            h1_present = False
            ldjson_present = False
            og_count = 0
            alt_ratio = 0.0
            abs_link_count = 0
            viewport_present = False
            is_https = False
            script_count = 0
            css_count = 0

        else:
            # HTML signal extraction
            title_present = bool(TITLE_RE.search(html))
            meta_desc_present = bool(META_DESC_RE.search(html))
            h1_present = bool(H1_RE.search(html))
            viewport_present = bool(VIEWPORT_RE.search(html))
            canonical_present = bool(CANONICAL_RE.search(html))
            robots_noindex = bool(ROBOTS_NOIDX_RE.search(html))
            og_count = len(OG_TAG_RE.findall(html))
            ldjson_present = bool(LDJSON_RE.search(html))
            img_count = len(IMG_TAG_RE.findall(html))
            img_alt_count = len(IMG_ALT_RE.findall(html))
            alt_ratio = (img_alt_count / img_count * 100.0) if img_count > 0 else 100.0
            link_count = len(A_TAG_RE.findall(html))
            abs_link_count = len(ABS_LINK_RE.findall(html))
            script_count = len(SCRIPT_TAG_RE.findall(html))
            css_count = len(CSS_LINK_RE.findall(html))
            hreflang_count = len(HREFLANG_RE.findall(html))
            is_https = url.lower().startswith("https://") if url else False
            mixed_content = bool(MIXED_HTTP_RE.search(html)) if (is_https and html) else False

            # Category scoring
            onpage_score = weighted_average(
                {
                    "Title": to_pct(title_present),
                    "Meta Description": to_pct(meta_desc_present),
                    "H1": to_pct(h1_present),
                    "Structured Data": to_pct(ldjson_present),
                    "Open Graph": clamp(og_count * 20.0),
                    "Image Alt Ratio": alt_ratio,
                    "Canonical": to_pct(canonical_present),
                },
                {
                    "Title": 0.18,
                    "Meta Description": 0.18,
                    "H1": 0.12,
                    "Structured Data": 0.12,
                    "Open Graph": 0.10,
                    "Image Alt Ratio": 0.20,
                    "Canonical": 0.10,
                },
            )

            security_score = weighted_average(
                {
                    "HTTPS": to_pct(is_https),
                    "Mixed Content": 100.0 if not mixed_content else 0.0,
                },
                {"HTTPS": 0.6, "Mixed Content": 0.4},
            )

            mobile_score = to_pct(viewport_present)

            perf_score = weighted_average(
                {
                    "Page Size": page_size_score(page_bytes),
                    "External Scripts": inverse_count_score(script_count, max_good=3, max_bad=20),
                    "CSS Sheets": inverse_count_score(css_count, max_good=2, max_bad=15),
                },
                {"Page Size": 0.6, "External Scripts": 0.2, "CSS Sheets": 0.2},
            )

            crawl_score = weighted_average(
                {
                    "Canonical": to_pct(canonical_present),
                    "Noindex": 100.0 if not robots_noindex else 0.0,
                    "Hreflang": clamp(hreflang_count * 20.0),
                    "Reasonable Links": clamp(min(link_count, 80) / 80 * 100.0 if link_count else 0.0),
                },
                {"Canonical": 0.35, "Noindex": 0.35, "Hreflang": 0.15, "Reasonable Links": 0.15},
            )

            category_scores = {
                "On-Page SEO": round(onpage_score, 1),
                "Security": round(security_score, 1),
                "Mobile": round(mobile_score, 1),
                "Performance": round(perf_score, 1),
                "Crawlability": round(crawl_score, 1),
            }

            overall_score = round(
                weighted_average(
                    category_scores,
                    {
                        "On-Page SEO": 0.35,
                        "Security": 0.20,
                        "Mobile": 0.10,
                        "Performance": 0.20,
                        "Crawlability": 0.15,
                    },
                ),
                1,
            )
            grade = grade_from_score(overall_score)

            # Rich executive content
            executive_text = (
                f"Professional SEO Audit for {url}\n\n"
                "This single-page analysis evaluates key on-page SEO elements, security protocols, "
                "mobile responsiveness, performance metrics, and crawlability signals from the HTML source.\n\n"
                "FF Tech provides instant, actionable insights to optimize your site. For full site-wide "
                "audits including backlinks and competitors, enable advanced modules."
            )

            strengths = []
            weaknesses = []
            priority_fixes = []

            if is_https:
                strengths.append("🔒 HTTPS Securely Implemented")
            else:
                weaknesses.append("⚠️ HTTPS Missing")
                priority_fixes.append("Implement SSL/HTTPS across the site for security and SEO benefits.")

            if title_present:
                strengths.append("📝 Title Tag Present")
            else:
                weaknesses.append("❌ Title Tag Missing")
                priority_fixes.append("Add unique, keyword-rich <title> tags to improve click-through rates.")

            if meta_desc_present:
                strengths.append("📄 Meta Description Present")
            else:
                weaknesses.append("❌ Meta Description Missing")
                priority_fixes.append("Craft engaging meta descriptions under 160 characters for better SERP performance.")

            if canonical_present:
                strengths.append("✅ Canonical Tag Detected")
            else:
                weaknesses.append("⚠️ Canonical Tag Missing")
                priority_fixes.append("Add rel=\"canonical\" tags to avoid duplicate content penalties.")

            if ldjson_present:
                strengths.append("🧩 Structured Data (JSON-LD) Found")
            else:
                priority_fixes.append("Implement structured data for rich snippets and enhanced visibility.")

            if viewport_present:
                strengths.append("📱 Mobile Viewport Configured")
            else:
                weaknesses.append("⚠️ Viewport Meta Missing")
                priority_fixes.append("Add viewport meta tag for responsive mobile design.")

            if og_count > 0:
                strengths.append("🎨 Open Graph Tags for Social Sharing")

            if mixed_content:
                weaknesses.append("🔥 Mixed Content Issues Detected")
                priority_fixes.append("Resolve HTTP resources on HTTPS pages to prevent security warnings.")

            if not strengths:
                strengths = ["Basic page structure detected – ready for optimization."]
            if not weaknesses:
                weaknesses = ["No major foundational issues found."]
            if not priority_fixes:
                priority_fixes = ["Site foundations are solid – consider deeper analysis for growth opportunities."]

            rows = [
                {"label": "Overall Health Score", "value": overall_score},
                {"label": "On-Page SEO", "value": category_scores["On-Page SEO"]},
                {"label": "Security", "value": category_scores["Security"]},
                {"label": "Mobile", "value": category_scores["Mobile"]},
                {"label": "Performance", "value": category_scores["Performance"]},
                {"label": "Crawlability", "value": category_scores["Crawlability"]},
                {"label": "Title Tag Present", "value": to_pct(title_present)},
                {"label": "Meta Description Present", "value": to_pct(meta_desc_present)},
                {"label": "H1 Present", "value": to_pct(h1_present)},
                {"label": "Structured Data Present", "value": to_pct(ldjson_present)},
                {"label": "Open Graph Tags Present", "value": to_pct(og_count > 0)},
                {"label": "Viewport Meta Present", "value": to_pct(viewport_present)},
                {"label": "Canonical Present", "value": to_pct(canonical_present)},
                {"label": "Mixed Content Detected", "value": to_pct(mixed_content)},
                {"label": "Image Alt Coverage (%)", "value": alt_ratio},
            ]

        # Metrics dictionary – always include all keys for compatibility
        metrics: Dict[str, Any] = {
            # Executive
            "overall.health_score": overall_score,
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
            "summary.presentation_standard": "Premium SaaS Layout",
            "summary.print_ready": True,

            # Site health
            "health.score": overall_score,
            "health.audit_completion_status": "Complete" if analyzed else "Awaiting URL",

            # Crawlability
            "crawl.missing_canonical_tags": 0 if canonical_present else 1 if analyzed else None,
            "crawl.hreflang_errors": 0 if hreflang_count >= 1 else 1 if analyzed else None,
            "crawl.hreflang_conflicts": None,

            # On-page
            "onpage.missing_title_tags": 0 if title_present else 1 if analyzed else None,
            "onpage.missing_meta_descriptions": 0 if meta_desc_present else 1 if analyzed else None,
            "onpage.missing_h1": 0 if h1_present else 1 if analyzed else None,
            "onpage.missing_structured_data": 0 if ldjson_present else 1 if analyzed else None,
            "onpage.missing_open_graph_tags": 0 if og_count > 0 else 1 if analyzed else None,
            "onpage.external_links_count": abs_link_count if analyzed else None,
            "onpage.missing_image_alt_tags": 0 if alt_ratio >= 60.0 else 1 if analyzed else None,

            # Performance
            "perf.total_page_size": page_bytes if analyzed else None,
            "perf.requests_per_page": script_count + css_count if analyzed else None,
            "perf.render_blocking_resources": css_count if analyzed else None,

            # Mobile/Security/Social
            "mobile.viewport_meta_tag": viewport_present if analyzed else None,
            "mobile.mobile_friendly": viewport_present if analyzed else None,  # proxy
            "security.https_implementation": is_https if analyzed else None,
            "security.mixed_content": mixed_content if analyzed else None,
            "index.noindex_issues": robots_noindex if analyzed else None,
            "social.metadata_presence": og_count > 0 if analyzed else None,

            # Raw signals
            "page.bytes": page_bytes if analyzed else None,
            "http.status": status if analyzed else None,
            "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",

            # UI rows
            "rows": rows,
        }

        # Fill remaining keys with None
        for key in ALL_KEYS:
            if key not in metrics:
                metrics[key] = None

        return metrics


# ---------------------------
# PDF Report Generator (Premium, Branded Design)
# ---------------------------
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm


def _draw_header(c: canvas.Canvas, title: str, url: str, page_no: int) -> None:
    width, _ = A4
    c.setFillColor(colors.HexColor("#4f46e5"))  # Premium indigo
    c.rect(0, 27 * cm, width, 3 * cm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, 28.5 * cm, "FF Tech AI Website Audit")
    c.setFont("Helvetica", 12)
    c.drawCentredString(width / 2, 27.8 * cm, title)
    c.setFillColor(colors.grey)
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, 27.2 * cm, f"Target: {url}")
    c.drawRightString(width - 2 * cm, 27.2 * cm, f"Page {page_no}/5")


def _draw_bar(
    c: canvas.Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    pct: float | None,
    label: str,
) -> None:
    if pct is None:
        c.setFillColor(colors.grey)
        c.drawString(x, y + height / 2 - 0.2 * cm, f"{label} – Pending Analysis")
        return
    pct = clamp(pct)
    # Background
    c.setFillColor(colors.HexColor("#e5e7eb"))
    c.rect(x, y, width, height, fill=1, stroke=0)
    # Fill (gradient-like with premium color)
    c.setFillColor(colors.HexColor("#6366f1"))
    c.rect(x, y, width * (pct / 100.0), height, fill=1, stroke=0)
    # Label
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + 0.5 * cm, y + height / 2 - 0.2 * cm, f"{label} – {pct:.1f}%")


def generate_pdf_report(url: str, metrics: Dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # Page 1 – Executive Summary
    _draw_header(c, "Executive Summary", url, 1)
    grade = metrics.get("overall.grade", "—")
    score = metrics.get("overall.health_score", None)
    y = 24 * cm
    c.setFont("Helvetica-Bold", 48)
    c.setFillColor(colors.HexColor("#10b981" if score and score > 70 else "#ef4444"))
    c.drawCentredString(width / 2, y, grade)
    if score is not None:
        c.setFont("Helvetica", 18)
        c.drawCentredString(width / 2, y - 2 * cm, f"{score:.1f}% Overall Score")
    else:
        c.setFont("Helvetica-Bold", 24)
        c.drawCentredString(width / 2, y - 2 * cm, "Enter URL to Audit")
    c.setFont("Helvetica", 12)
    c.drawString(2 * cm, y - 4 * cm, metrics.get("summary.executive_text", ""))
    c.showPage()

    # Page 2 – Category Breakdown
    _draw_header(c, "Category Breakdown", url, 2)
    cat = metrics.get("summary.category_breakdown", {})
    y = 24 * cm
    for label, key in [
        ("On-Page SEO", "On-Page SEO"),
        ("Security", "Security"),
        ("Mobile", "Mobile"),
        ("Performance", "Performance"),
        ("Crawlability", "Crawlability"),
    ]:
        _draw_bar(c, 2 * cm, y, 16 * cm, 0.8 * cm, cat.get(key), label)
        y -= 1.5 * cm
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, 6 * cm, "Focus on low-scoring categories for quick improvements.")
    c.showPage()

    # Page 3 – Strengths & Weaknesses
    _draw_header(c, "Strengths & Weaknesses", url, 3)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2 * cm, 25 * cm, "Strengths ✅")
    c.setFont("Helvetica", 10)
    y = 24 * cm
    for s in metrics.get("summary.strengths", []):
        c.drawString(2 * cm, y, f"• {s}")
        y -= 0.7 * cm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2 * cm, y - 1 * cm, "Weaknesses ⚠️")
    y -= 1.5 * cm
    c.setFont("Helvetica", 10)
    for w in metrics.get("summary.weaknesses", []):
        c.drawString(2 * cm, y, f"• {w}")
        y -= 0.7 * cm
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, 6 * cm, "Leverage strengths and address weaknesses to boost performance.")
    c.showPage()

    # Page 4 – Priority Fixes
    _draw_header(c, "Priority Fixes & Roadmap", url, 4)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2 * cm, 25 * cm, "Recommended Actions")
    c.setFont("Helvetica", 10)
    y = 24 * cm
    for f in metrics.get("summary.priority_fixes", []):
        c.drawString(2 * cm, y, f"• {f}")
        y -= 0.7 * cm
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, 6 * cm, "Implement these fixes in priority order for maximum impact.")
    c.showPage()

    # Page 5 – Certification
    _draw_header(c, "Certified Report", url, 5)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2 * cm, 25 * cm, "Certification")
    c.setFont("Helvetica", 12)
    c.drawString(2 * cm, 24 * cm, "This report is generated by FF Tech AI Website Audit SaaS.")
    c.drawString(2 * cm, 23 * cm, "For comprehensive site-wide insights, contact us for premium features.")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2 * cm, 21 * cm, f"Grade: {grade}")
    c.drawString(2 * cm, 20 * cm, f"Score: {score:.1f}%" if score else "Pending")
    c.setFont("Helvetica", 9)
    c.drawString(2 * cm, 6 * cm, f"Generated: {metrics.get('generated_at', '')}")
    c.showPage()

    c.save()
    buf.seek(0)
    return buf.read()
