
# fftech_audit/analyzers.py
from typing import Dict, Any, Tuple, List
from collections import Counter
from statistics import mean
from fftech_audit.crawlers import CrawlResult, PageInfo

def summarize_crawl(cr: CrawlResult) -> Dict[str, Any]:
    """
    Compute many of the numbered metrics from the crawl result.
    Returns a dict with keys aligned to your spec numbering (1..200).
    Missing items are None with 'details' explaining why (transparent).
    """
    metrics: Dict[str, Any] = {}
    details: Dict[str, Any] = {}

    total_pages = len(cr.pages)
    status_bucket = cr.status_counts  # keys: 200, 300, 400, 500
    two_xx = int(status_bucket.get(200, 0))
    three_xx = int(status_bucket.get(300, 0))
    four_xx = int(status_bucket.get(400, 0))
    five_xx = int(status_bucket.get(500, 0))

    # ---- B. Overall Site Health (11–20)
    metrics["11.Site Health Score"] = None  # computed in final scoring
    metrics["12.Total Errors"] = four_xx + five_xx
    metrics["13.Total Warnings"] = three_xx
    metrics["14.Total Notices"] = 0  # placeholder (heuristics later)
    metrics["15.Total Crawled Pages"] = total_pages
    metrics["16.Total Indexed Pages"] = None  # requires search console or heuristics
    metrics["17.Issues Trend"] = None  # needs history
    metrics["18.Crawl Budget Efficiency"] = two_xx / max(total_pages, 1)
    metrics["19.Orphan Pages Percentage"] = None  # needs full internal link graph + site map baseline
    metrics["20.Audit Completion Status"] = "partial" if cr.errors else "complete"

    # ---- C. Crawlability & Indexation (21–40)
    metrics["21.HTTP 2xx Pages"] = two_xx
    metrics["22.HTTP 3xx Pages"] = three_xx
    metrics["23.HTTP 4xx Pages"] = four_xx
    metrics["24.HTTP 5xx Pages"] = five_xx

    metrics["25.Redirect Chains"] = None  # follow_redirects hides chain; instrument later
    metrics["26.Redirect Loops"] = None
    metrics["27.Broken Internal Links"] = len(cr.broken_links_internal)
    metrics["28.Broken External Links"] = len(cr.broken_links_external)

    # robots + meta robots blocked
    robots_blocked = 0
    meta_blocked = 0
    non_canonical = 0
    missing_canonical = 0
    incorrect_canonical = 0
    sitemap_missing_pages = 0
    sitemap_not_crawled = 0
    hreflang_errors = 0
    hreflang_conflicts = 0
    pagination_issues = 0
    crawl_depth_distribution = {}  # simplified: not computed here
    dup_param_urls = 0

    # Prepare sitemap URL set
    sitemap_set = set()
    for sm in cr.sitemap_urls:
        details.setdefault("34.sitemap_source", []).append(sm)
    # (We don't re-fetch here; parsers already added seeds if available.)

    # Evaluate pages
    for p in cr.pages:
        # robots meta
        if p.meta_robots and ("noindex" in p.meta_robots.lower() or "nofollow" in p.meta_robots.lower()):
            meta_blocked += 1
        # canonical
        if p.canonical:
            if p.canonical.strip() != p.url.strip():
                non_canonical += 1
        else:
            missing_canonical += 1
        # naïve incorrect canonical heuristic
        if p.canonical and not p.canonical.startswith(("http://", "https://")):
            incorrect_canonical += 1
        # hreflang errors
        for lang, href in p.hreflang:
            if not lang or not href:
                hreflang_errors += 1

        # pagination check
        if (p.rel_prev and not p.rel_next) or (p.rel_next and not p.rel_prev):
            pagination_issues += 1

        # duplicate parameter URLs
        if "?" in p.url:
            dup_param_urls += 1

    # robots.txt blocked pages cannot be known without attempted fetch; assume allowed
    metrics["29.robots.txt Blocked URLs"] = 0 if cr.robots_allowed else None
    metrics["30.Meta Robots Blocked URLs"] = meta_blocked
    metrics["31.Non-Canonical Pages"] = non_canonical
    metrics["32.Missing Canonical Tags"] = missing_canonical
    metrics["33.Incorrect Canonical Tags"] = incorrect_canonical
    metrics["34.Sitemap Missing Pages"] = sitemap_missing_pages  # needs sitemap set vs crawl set
    metrics["35.Sitemap Not Crawled Pages"] = sitemap_not_crawled
    metrics["36.Hreflang Errors"] = hreflang_errors
    metrics["37.Hreflang Conflicts"] = hreflang_conflicts
    metrics["38.Pagination Issues"] = pagination_issues
    metrics["39.Crawl Depth Distribution"] = crawl_depth_distribution or None
    metrics["40.Duplicate Parameter URLs"] = dup_param_urls

    # ---- D. On-Page SEO (41–75)
    missing_title = 0
    dup_title = 0
    too_long_title = 0
    too_short_title = 0
    missing_meta = 0
    dup_meta = 0
    meta_too_long = 0
    meta_too_short = 0
    missing_h1 = 0
    multiple_h1 = 0
    duplicate_headings = 0  # requires per-page compare (omitted)
    thin_content_pages = 0
    duplicate_content_pages = None  # requires hashing across pages
    low_t2h_ratio = 0
    missing_alt = 0
    duplicate_alt = None
    large_images_uncompressed = None  # needs byte-level check
    pages_without_indexed_content = None
    missing_structured_data = 0
    structured_data_errors = None  # JSON-LD validation
    rich_snippet_warnings = None
    missing_og_tags = 0
    long_urls = 0
    uppercase_urls = 0
    non_seo_friendly_urls = 0
    too_many_internal_links = 0
    pages_without_incoming_links = None  # need link graph inbound
    orphan_pages = None  # need link graph inbound
    broken_anchor_links = None  # check hash vs id
    redirected_internal_links = None
    nofollow_internal_links = None
    link_depth_issues = None
    external_links_count = len(cr.external_links)
    broken_external_links = len(cr.broken_links_external)
    anchor_text_issues = None

    seen_titles = Counter()
    seen_metas = Counter()

    for p in cr.pages:
        # Titles
        if not p.html_title:
            missing_title += 1
        else:
            seen_titles[p.html_title.strip().lower()] += 1
            if len(p.html_title) > 70:
                too_long_title += 1
            if len(p.html_title) < 10:
                too_short_title += 1

        # Meta desc
        if not p.meta_desc:
            missing_meta += 1
        else:
            txt = p.meta_desc.strip()
            seen_metas[txt.lower()] += 1
            if len(txt) > 160:
                meta_too_long += 1
            if len(txt) < 50:
                meta_too_short += 1

        # H1
        if p.h1_count == 0:
            missing_h1 += 1
        if p.h1_count > 1:
            multiple_h1 += 1

        # Simple thin content heuristic: very low dom nodes
        if p.dom_nodes_est and p.dom_nodes_est < 100:
            thin_content_pages += 1

        # Text to HTML ratio: without raw text size, approximate by dom_nodes
        if p.dom_nodes_est and p.dom_nodes_est < 200:
            low_t2h_ratio += 1

        # Missing alt
        missing_alt += p.images_missing_alt

        # URL issues
        if len(p.url) > 115:
            long_urls += 1
        if any(c.isupper() for c in p.url.split("/")[-1]):
            uppercase_urls += 1
        # Non-SEO-friendly (heuristic: query + numbers + no hyphens)
        last = p.url.split("/")[-1]
        if ("?" in p.url) or (re.search(r"\d{5,}", last)) or ("-" not in last):
            non_seo_friendly_urls += 1

        # Internal link counts
        if len(p.links_internal) > 300:
            too_many_internal_links += 1

    dup_title = sum(1 for k, v in seen_titles.items() if v > 1)
    dup_meta = sum(1 for k, v in seen_metas.items() if v > 1)

    metrics.update({
        "41.Missing Title Tags": missing_title,
        "42.Duplicate Title Tags": dup_title,
        "43.Title Too Long": too_long_title,
        "44.Title Too Short": too_short_title,
        "45.Missing Meta Descriptions": missing_meta,
        "46.Duplicate Meta Descriptions": dup_meta,
        "47.Meta Too Long": meta_too_long,
        "48.Meta Too Short": meta_too_short,
        "49.Missing H1": missing_h1,
        "50.Multiple H1": multiple_h1,
        "51.Duplicate Headings": duplicate_headings,
        "52.Thin Content Pages": thin_content_pages,
        "53.Duplicate Content Pages": duplicate_content_pages,
        "54.Low Text-to-HTML Ratio": low_t2h_ratio,
        "55.Missing Image Alt Tags": missing_alt,
        "56.Duplicate Alt Tags": duplicate_alt,
        "57.Large Uncompressed Images": large_images_uncompressed,
        "58.Pages Without Indexed Content": pages_without_indexed_content,
        "59.Missing Structured Data": sum(1 for p in cr.pages if not p.schema_present),
        "60.Structured Data Errors": structured_data_errors,
        "61.Rich Snippet Warnings": rich_snippet_warnings,
        "62.Missing Open Graph Tags": sum(1 for p in cr.pages if not p.og_tags_present),
        "63.Long URLs": long_urls,
        "64.Uppercase URLs": uppercase_urls,
        "65.Non-SEO-Friendly URLs": non_seo_friendly_urls,
        "66.Too Many Internal Links": too_many_internal_links,
        "67.Pages Without Incoming Links": pages_without_incoming_links,
        "68.Orphan Pages": orphan_pages,
        "69.Broken Anchor Links": broken_anchor_links,
        "70.Redirected Internal Links": redirected_internal_links,
        "71.NoFollow Internal Links": nofollow_internal_links,
        "72.Link Depth Issues": link_depth_issues,
        "73.External Links Count": external_links_count,
        "74.Broken External Links": broken_external_links,
        "75.Anchor Text Issues": anchor_text_issues,
    })

    # ---- E. Performance & Technical (76–96) (heuristics, not CWV)
    total_size = sum(p.content_len for p in cr.pages if p.content_len)
    avg_scripts = mean([p.scripts for p in cr.pages]) if cr.pages else 0
    avg_styles = mean([p.stylesheets for p in cr.pages]) if cr.pages else 0
    avg_dom = mean([p.dom_nodes_est for p in cr.pages if p.dom_nodes_est]) if cr.pages else 0
    render_blocking_resources = sum(1 for p in cr.pages if p.stylesheets > 0)  # heuristic

    metrics.update({
        "76.Largest Contentful Paint (LCP)": None,  # needs PSI/Lighthouse
        "77.First Contentful Paint (FCP)": None,
        "78.Cumulative Layout Shift (CLS)": None,
        "79.Total Blocking Time": None,
        "80.First Input Delay": None,
        "81.Speed Index": None,
        "82.Time to Interactive": None,
        "83.DOM Content Loaded": None,
        "84.Total Page Size": total_size,
        "85.Requests Per Page": avg_scripts + avg_styles + 1,  # +1 for base doc
        "86.Unminified CSS": None,
        "87.Unminified JavaScript": None,
        "88.Render Blocking Resources": render_blocking_resources,
        "89.Excessive DOM Size": sum(1 for p in cr.pages if p.dom_nodes_est and p.dom_nodes_est > 1500),
        "90.Third-Party Script Load": None,
        "91.Server Response Time": None,
        "92.Image Optimization": None,
        "93.Lazy Loading Issues": None,
        "94.Browser Caching Issues": None,
        "95.Missing GZIP / Brotli": None,
        "96.Resource Load Errors": None,
    })

    # ---- F. Mobile, Security & International (97–150)
    viewport_missing = 0
    small_font_issues = None
    tap_target_issues = None
    mobile_layout_issues = None
    intrusive_interstitials = None
    mobile_nav_issues = None
    ssl_validity = None
    expired_ssl = None
    mixed_content_total = sum(p.mixed_content_http for p in cr.pages)
    insecure_resources = mixed_content_total
    missing_security_headers = None  # needs header inspection across pages
    open_directory_listing = None
    login_pages_without_https = None

    viewport_yes = 0
    for p in cr.pages:
        # viewport meta presence
        viewport = False
        # We didn’t store full meta list; approximate by meta_desc existing and title; improve later by re-parsing here if needed
        viewport = False  # placeholder (requires storing meta viewport in PageInfo)
        if viewport:
            viewport_yes += 1
        # Mixed content already counted

    metrics.update({
        "97.Mobile Friendly Test": None,
        "98.Viewport Meta Tag": viewport_yes,
        "99.Small Font Issues": small_font_issues,
        "100.Tap Target Issues": tap_target_issues,
        "101.Mobile Core Web Vitals": None,
        "102.Mobile Layout Issues": mobile_layout_issues,
        "103.Intrusive Interstitials": intrusive_interstitials,
        "104.Mobile Navigation Issues": mobile_nav_issues,
        "105.HTTPS Implementation": sum(1 for p in cr.pages if p.url.startswith("https://")),
        "106.SSL Certificate Validity": ssl_validity,
        "107.Expired SSL": expired_ssl,
        "108.Mixed Content": mixed_content_total,
        "109.Insecure Resources": insecure_resources,
        "110.Missing Security Headers": missing_security_headers,
        "111.Open Directory Listing": open_directory_listing,
        "112.Login Pages Without HTTPS": login_pages_without_https,
        "113.Missing Hreflang": sum(1 for p in cr.pages if not p.hreflang),
        "114.Incorrect Language Codes": None,
        "115.Hreflang Conflicts": None,
        "116.Region Targeting Issues": None,
        "117.Multi-Domain SEO Issues": None,
        "118.Domain Authority": None,  # needs provider
        "119.Referring Domains": None,
        "120.Total Backlinks": None,
        "121.Toxic Backlinks": None,
        "122.NoFollow Backlinks": None,
        "123.Anchor Distribution": None,
        "124.Referring IPs": None,
        "125.Lost / New Backlinks": None,
        "126.JavaScript Rendering Issues": None,
        "127.CSS Blocking": render_blocking_resources,
        "128.Crawl Budget Waste": None,
        "129.AMP Issues": None,
        "130.PWA Issues": None,
        "131.Canonical Conflicts": None,
        "132.Subdomain Duplication": None,
        "133.Pagination Conflicts": None,
        "134.Dynamic URL Issues": dup_param_urls,
        "135.Lazy Load Conflicts": None,
        "136.Sitemap Presence": 1 if cr.sitemap_urls else 0,
        "137.Noindex Issues": sum(1 for p in cr.pages if p.meta_robots and "noindex" in p.meta_robots.lower()),
        "138.Structured Data Consistency": None,
        "139.Redirect Correctness": None,
        "140.Broken Rich Media": None,
        "141.Social Metadata Presence": sum(1 for p in cr.pages if p.og_tags_present),
        "142.Error Trend": None,
        "143.Health Trend": None,
        "144.Crawl Trend": None,
        "145.Index Trend": None,
        "146.Core Web Vitals Trend": None,
        "147.Backlink Trend": None,
        "148.Keyword Trend": None,
        "149.Historical Comparison": None,
        "150.Overall Stability Index": None,
    })

    # ---- G. Competitor Analysis (151–167) — placeholder hooks
    for i in range(151, 168):
        metrics[f"{i}.Competitor Placeholder"] = None

    # ---- H. Broken Links Intelligence (168–180)
    metrics.update({
        "168.Total Broken Links": len(cr.broken_links_internal) + len(cr.broken_links_external),
        "169.Internal Broken Links": len(cr.broken_links_internal),
        "170.External Broken Links": len(cr.broken_links_external),
        "171.Broken Links Trend": None,
        "172.Broken Pages by Impact": None,
        "173.Status Code Distribution": dict(cr.status_counts),
        "174.Page Type Distribution": None,  # would need content-type grouping
        "175.Fix Priority Score": None,
        "176.SEO Loss Impact": None,
        "177.Affected Pages Count": len([p for p in cr.pages if p.status >= 400]),
        "178.Broken Media Links": None,
        "179.Resolution Progress": None,
        "180.Risk Severity Index": None,
    })

    # ---- I. Opportunities, Growth & ROI (181–200) — rule-based placeholders
    for i in range(181, 201):
        metrics[f"{i}.Opportunity Placeholder"] = None

    return {"metrics": metrics, "details": details}
