
# fftech_audit/analyzers.py
import re  # <-- required for regex checks
from typing import Dict, Any
from collections import Counter
from statistics import mean
from fftech_audit.crawlers import CrawlResult

def summarize_crawl(cr: CrawlResult) -> Dict[str, Any]:
    """
    Compute numbered metrics from the crawl result.
    Returns a dict with 'metrics' and 'details'.
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
    metrics["11.Site Health Score"] = None  # computed by scorer
    metrics["12.Total Errors"] = four_xx + five_xx
    metrics["13.Total Warnings"] = three_xx
    metrics["14.Total Notices"] = 0
    metrics["15.Total Crawled Pages"] = total_pages
    metrics["16.Total Indexed Pages"] = None
    metrics["17.Issues Trend"] = None
    metrics["18.Crawl Budget Efficiency"] = two_xx / max(total_pages, 1)
    metrics["19.Orphan Pages Percentage"] = None
    metrics["20.Audit Completion Status"] = "partial" if cr.errors else "complete"

    # ---- C. Crawlability & Indexation (21–40)
    metrics["21.HTTP 2xx Pages"] = two_xx
    metrics["22.HTTP 3xx Pages"] = three_xx
    metrics["23.HTTP 4xx Pages"] = four_xx
    metrics["24.HTTP 5xx Pages"] = five_xx
    metrics["25.Redirect Chains"] = None
    metrics["26.Redirect Loops"] = None
    metrics["27.Broken Internal Links"] = len(cr.broken_links_internal)
    metrics["28.Broken External Links"] = len(cr.broken_links_external)

    meta_blocked = 0
    non_canonical = 0
    missing_canonical = 0
    incorrect_canonical = 0
    hreflang_errors = 0
    pagination_issues = 0
    dup_param_urls = 0

    for p in cr.pages:
        # meta robots
        if p.meta_robots and ("noindex" in p.meta_robots.lower() or "nofollow" in p.meta_robots.lower()):
            meta_blocked += 1

        # canonical
        if p.canonical:
            if p.canonical.strip() != p.url.strip():
                non_canonical += 1
            # incorrect canonical (not absolute URL)
            if not p.canonical.startswith(("http://", "https://")):
                incorrect_canonical += 1
        else:
            missing_canonical += 1

        # hreflang
        for lang, href in p.hreflang:
            if not lang or not href:
                hreflang_errors += 1

        # pagination rels
        if (p.rel_prev and not p.rel_next) or (p.rel_next and not p.rel_prev):
            pagination_issues += 1

        # duplicate parameter URLs
        if "?" in p.url:
            dup_param_urls += 1

    metrics["29.robots.txt Blocked URLs"] = 0 if cr.robots_allowed else None
    metrics["30.Meta Robots Blocked URLs"] = meta_blocked
    metrics["31.Non-Canonical Pages"] = non_canonical
    metrics["32.Missing Canonical Tags"] = missing_canonical
    metrics["33.Incorrect Canonical Tags"] = incorrect_canonical
    metrics["34.Sitemap Missing Pages"] = None
    metrics["35.Sitemap Not Crawled Pages"] = None
    metrics["36.Hreflang Errors"] = hreflang_errors
    metrics["37.Hreflang Conflicts"] = None
    metrics["38.Pagination Issues"] = pagination_issues
    metrics["39.Crawl Depth Distribution"] = None
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
    thin_content_pages = 0
    low_t2h_ratio = 0
    missing_alt = 0
    long_urls = 0
    uppercase_urls = 0
    non_seo_friendly_urls = 0
    too_many_internal_links = 0

    seen_titles = Counter()
    seen_metas = Counter()

    for p in cr.pages:
        # Titles
        if not p.html_title:
            missing_title += 1
        else:
            title = p.html_title.strip()
            seen_titles[title.lower()] += 1
            if len(title) > 70:
                too_long_title += 1
            if len(title) < 10:
                too_short_title += 1

        # Meta description
        if not p.meta_desc:
            missing_meta += 1
        else:
            desc = p.meta_desc.strip()
            seen_metas[desc.lower()] += 1
            if len(desc) > 160:
                meta_too_long += 1
            if len(desc) < 50:
                meta_too_short += 1

        # H1
        if p.h1_count == 0:
            missing_h1 += 1
        if p.h1_count > 1:
            multiple_h1 += 1

        # Thin content / low text-to-HTML ratio (heuristic: small DOM)
        if p.dom_nodes_est and p.dom_nodes_est < 100:
            thin_content_pages += 1
        if p.dom_nodes_est and p.dom_nodes_est < 200:
            low_t2h_ratio += 1

        # Missing alt tags
        missing_alt += p.images_missing_alt

        # URL issues
        last = p.url.split("/")[-1] if "/" in p.url else p.url
        if len(p.url) > 115:
            long_urls += 1
        if any(c.isupper() for c in (last or "")):
            uppercase_urls += 1
        # Non-SEO-friendly (query string, long number sequences, or no hyphens)
        if ("?" in p.url) or (re.search(r"\d{5,}", last or "")) or ("-" not in (last or "")):
            non_seo_friendly_urls += 1

        # Internal link counts
        if len(p.links_internal) > 300:
            too_many_internal_links += 1

    dup_title = sum(1 for _, v in seen_titles.items() if v > 1)
    dup_meta = sum(1 for _, v in seen_metas.items() if v > 1)

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
        "51.Duplicate Headings": None,
        "52.Thin Content Pages": thin_content_pages,
        "53.Duplicate Content Pages": None,
        "54.Low Text-to-HTML Ratio": low_t2h_ratio,
        "55.Missing Image Alt Tags": missing_alt,
        "56.Duplicate Alt Tags": None,
        "57.Large Uncompressed Images": None,
        "58.Pages Without Indexed Content": None,
        "59.Missing Structured Data": sum(1 for p in cr.pages if not p.schema_present),
        "60.Structured Data Errors": None,
        "61.Rich Snippet Warnings": None,
        "62.Missing Open Graph Tags": sum(1 for p in cr.pages if not p.og_tags_present),
        "63.Long URLs": long_urls,
        "64.Uppercase URLs": uppercase_urls,
        "65.Non-SEO-Friendly URLs": non_seo_friendly_urls,
        "66.Too Many Internal Links": too_many_internal_links,
        "67.Pages Without Incoming Links": None,
        "68.Orphan Pages": None,
        "69.Broken Anchor Links": None,
        "70.Redirected Internal Links": None,
        "71.NoFollow Internal Links": None,
        "72.Link Depth Issues": None,
        "73.External Links Count": len(cr.external_links),
        "74.Broken External Links": len(cr.broken_links_external),
        "75.Anchor Text Issues": None,
    })

    # ---- E. Performance & Technical (76–96)
    total_size = sum(p.content_len for p in cr.pages if p.content_len)
    avg_scripts = mean([p.scripts for p in cr.pages]) if cr.pages else 0
    avg_styles = mean([p.stylesheets for p in cr.pages]) if cr.pages else 0
    render_blocking_resources = sum(1 for p in cr.pages if p.stylesheets > 0)
    metrics.update({
        "76.Largest Contentful Paint (LCP)": None,
        "77.First Contentful Paint (FCP)": None,
        "78.Cumulative Layout Shift (CLS)": None,
        "79.Total Blocking Time": None,
        "80.First Input Delay": None,
        "81.Speed Index": None,
        "82.Time to Interactive": None,
        "83.DOM Content Loaded": None,
        "84.Total Page Size": total_size,
        "85.Requests Per Page": avg_scripts + avg_styles + 1,  # heuristic
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

    # ---- F, G, H, I placeholders / computed items
    metrics.update({
        "97.Mobile Friendly Test": None,
        "98.Viewport Meta Tag": 0,  # not tracked yet
        "105.HTTPS Implementation": sum(1 for p in cr.pages if p.url.startswith("https://")),
        "108.Mixed Content": sum(p.mixed_content_http for p in cr.pages),
        "136.Sitemap Presence": 1 if cr.sitemap_urls else 0,
        "137.Noindex Issues": sum(1 for p in cr.pages if p.meta_robots and "noindex" in p.meta_robots.lower()),
        "168.Total Broken Links": len(cr.broken_links_internal) + len(cr.broken_links_external),
        "169.Internal Broken Links": len(cr.broken_links_internal),
        "170.External Broken Links": len(cr.broken_links_external),
        "173.Status Code Distribution": dict(cr.status_counts),
    })

    # placeholders for the rest to keep table comprehensive
    for i in list(range(99, 105)) + list(range(106, 136)) + list(range(138, 167)) + list(range(171, 180)) + list(range(181, 201)):
        key = f"{i}.Placeholder"
        if key not in metrics:
            metrics[key] = None

    return {"metrics": metrics, "details": details}
