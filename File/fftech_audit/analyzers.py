
# fftech_audit/analyzers.py (v2.1 — no-empty metrics + better totals)
from __future__ import annotations
import re
from typing import Dict, Any, List, Tuple
from collections import Counter
from statistics import mean
from urllib.parse import urlparse
import os
import json
import subprocess

class PageLike: ...
class CrawlResult: ...

def summarize_crawl(cr: CrawlResult) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    details: Dict[str, Any] = {}

    pages: List[PageLike] = getattr(cr, 'pages', []) or []
    total_pages = len(pages)

    # Normalize to avoid type surprises
    def _normalize_page(p):
        imgs = getattr(p, 'images', [])
        if isinstance(imgs, int):
            p.images = [{"src": None, "attrs": {}} for _ in range(int(imgs))]
        elif imgs is None:
            p.images = []
        p.images_missing_alt = int(getattr(p, 'images_missing_alt', 0) or 0)
        p.scripts = int(getattr(p, 'scripts', 0) or 0)
        p.stylesheets = int(getattr(p, 'stylesheets', 0) or 0)
        p.dom_nodes_est = int(getattr(p, 'dom_nodes_est', 0) or 0)
        p.response_ms = int(getattr(p, 'response_ms', 0) or 0)

    for p in pages:
        _normalize_page(p)

    status_bucket = getattr(cr, 'status_counts', {}) or {}
    two_xx = int(status_bucket.get(200, 0))
    three_xx = int(status_bucket.get(300, 0))
    four_xx = int(status_bucket.get(400, 0))
    five_xx = int(status_bucket.get(500, 0))

    # ---- Overall Site Health (11–20)
    metrics["11.Site Health Score"] = 0  # overwritten later
    metrics["12.Total Errors"] = four_xx + five_xx
    metrics["13.Total Warnings"] = three_xx
    metrics["14.Total Notices"] = 0
    metrics["15.Total Crawled Pages"] = total_pages
    meta_noindex_count = sum(1 for p in pages if getattr(p, 'meta_robots', '') and 'noindex' in str(p.meta_robots).lower())
    metrics["16.Total Indexed Pages"] = max(total_pages - meta_noindex_count, 0)
    metrics["17.Issues Trend"] = "n/a"
    metrics["18.Crawl Budget Efficiency"] = (two_xx / max(total_pages, 1)) if total_pages else 0.0
    metrics["19.Orphan Pages Percentage"] = 0.0
    metrics["20.Audit Completion Status"] = "complete" if total_pages > 0 and not getattr(cr, 'errors', []) else "partial"

    # ---- Crawlability & Indexation (21–40)
    metrics["21.HTTP 2xx Pages"] = two_xx
    metrics["22.HTTP 3xx Pages"] = three_xx
    metrics["23.HTTP 4xx Pages"] = four_xx
    metrics["24.HTTP 5xx Pages"] = five_xx
    metrics["25.Redirect Chains"] = len(getattr(cr, 'redirect_chains', []) or [])
    metrics["26.Redirect Loops"] = len(getattr(cr, 'redirect_loops', []) or [])
    metrics["27.Broken Internal Links"] = len(getattr(cr, 'broken_links_internal', []) or [])
    metrics["28.Broken External Links"] = len(getattr(cr, 'broken_links_external', []) or [])

    meta_blocked = 0
    non_canonical = 0
    missing_canonical = 0
    incorrect_canonical = 0
    hreflang_errors = 0
    pagination_issues = 0
    dup_param_urls = 0

    total_images = 0
    total_images_missing_alt = 0

    for p in pages:
        # tallies needed for scoring later
        total_images += len(getattr(p, 'images', []) or [])
        total_images_missing_alt += int(getattr(p, 'images_missing_alt', 0) or 0)

        meta_robots = str(getattr(p, 'meta_robots', '') or '')
        if 'noindex' in meta_robots.lower() or 'nofollow' in meta_robots.lower():
            meta_blocked += 1

        canonical = (getattr(p, 'canonical', '') or '').strip()
        url = (getattr(p, 'url', '') or '').strip()
        if canonical:
            if canonical != url:
                non_canonical += 1
            if not canonical.startswith(('http://', 'https://')):
                incorrect_canonical += 1
        else:
            missing_canonical += 1

        for pair in getattr(p, 'hreflang', []) or []:
            try:
                lang, href = pair
            except Exception:
                lang, href = None, None
            if not lang or not href:
                hreflang_errors += 1

        rel_prev = bool(getattr(p, 'rel_prev', False))
        rel_next = bool(getattr(p, 'rel_next', False))
        if (rel_prev and not rel_next) or (rel_next and not rel_prev):
            pagination_issues += 1

        if '?' in url:
            dup_param_urls += 1

    robots_blocked = getattr(cr, 'robots_blocked', []) or []
    metrics["29.robots.txt Blocked URLs"] = len(robots_blocked)
    metrics["30.Meta Robots Blocked URLs"] = meta_blocked
    metrics["31.Non-Canonical Pages"] = non_canonical
    metrics["32.Missing Canonical Tags"] = missing_canonical
    metrics["33.Incorrect Canonical Tags"] = incorrect_canonical

    sitemap_list = set(getattr(cr, 'sitemap_urls', []) or [])
    crawled_urls = set(getattr(p, 'url', '') for p in pages if getattr(p, 'url', None))
    metrics["34.Sitemap Missing Pages"] = len(sitemap_list - crawled_urls) if sitemap_list else 0
    metrics["35.Sitemap Not Crawled Pages"] = len(crawled_urls - sitemap_list) if sitemap_list else 0
    metrics["36.Hreflang Errors"] = hreflang_errors
    metrics["37.Hreflang Conflicts"] = 0
    metrics["38.Pagination Issues"] = pagination_issues
    depth_counts = Counter(int(getattr(p, 'depth', 0) or 0) for p in pages)
    metrics["39.Crawl Depth Distribution"] = dict(depth_counts)  # stringified later
    metrics["40.Duplicate Parameter URLs"] = dup_param_urls

    # ---- On-Page SEO (41–75)
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
    long_urls = 0
    uppercase_urls = 0
    non_seo_friendly_urls = 0
    too_many_internal_links = 0

    seen_titles = Counter()
    seen_metas = Counter()

    for p in pages:
        title = (getattr(p, 'html_title', '') or '').strip()
        if not title:
            missing_title += 1
        else:
            seen_titles[title.lower()] += 1
            if len(title) > 70: too_long_title += 1
            if len(title) < 10: too_short_title += 1

        desc = (getattr(p, 'meta_desc', '') or '').strip()
        if not desc:
            missing_meta += 1
        else:
            seen_metas[desc.lower()] += 1
            if len(desc) > 160: meta_too_long += 1
            if len(desc) < 50: meta_too_short += 1

        h1_count = int(getattr(p, 'h1_count', 0) or 0)
        if h1_count == 0: missing_h1 += 1
        if h1_count > 1: multiple_h1 += 1

        dom_nodes = int(getattr(p, 'dom_nodes_est', 0) or 0)
        if dom_nodes and dom_nodes < 100: thin_content_pages += 1
        if dom_nodes and dom_nodes < 200: low_t2h_ratio += 1

        url = getattr(p, 'url', '') or ''
        last = url.split('/')[-1] if '/' in url else url
        if len(url) > 115: long_urls += 1
        if any(c.isupper() for c in (last or '')): uppercase_urls += 1
        if ('?' in url) or (re.search(r"\d{5,}", last or "")) or ('-' not in (last or '')): non_seo_friendly_urls += 1

        if len(getattr(p, 'links_internal', []) or []) > 300: too_many_internal_links += 1

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
        "51.Duplicate Headings": 0,
        "52.Thin Content Pages": thin_content_pages,
        "53.Duplicate Content Pages": 0,
        "54.Low Text-to-HTML Ratio": low_t2h_ratio,
        "55.Missing Image Alt Tags": total_images_missing_alt,
        "56.Duplicate Alt Tags": 0,
        "57.Large Uncompressed Images": 0,
        "58.Pages Without Indexed Content": 0,
        "59.Missing Structured Data": sum(1 for p in pages if not getattr(p, 'schema_present', False)),
        "60.Structured Data Errors": 0,
        "61.Rich Snippet Warnings": 0,
        "62.Missing Open Graph Tags": sum(1 for p in pages if not getattr(p, 'og_tags_present', False)),
        "63.Long URLs": long_urls,
        "64.Uppercase URLs": uppercase_urls,
        "65.Non-SEO-Friendly URLs": non_seo_friendly_urls,
        "66.Too Many Internal Links": too_many_internal_links,
        "67.Pages Without Incoming Links": 0,
        "68.Orphan Pages": 0,
        "69.Broken Anchor Links": 0,
        "70.Redirected Internal Links": 0,
        "71.NoFollow Internal Links": 0,
        "72.Link Depth Issues": sum(1 for p in pages if int(getattr(p, 'depth', 0) or 0) >= 5),
        "73.External Links Count": len(getattr(cr, 'external_links', []) or []),
        "74.Broken External Links": len(getattr(cr, 'broken_links_external', []) or []),
        "75.Anchor Text Issues": 0,
    })

    # ---- Performance & Technical (76–96)
    total_size = sum(int(getattr(p, 'content_len', 0) or 0) for p in pages)
    avg_page_size = total_size / max(total_pages, 1)
    avg_scripts = mean([int(getattr(p, 'scripts', 0) or 0) for p in pages]) if pages else 0
    avg_styles = mean([int(getattr(p, 'stylesheets', 0) or 0) for p in pages]) if pages else 0
    avg_images = mean([len(getattr(p, 'images', []) or []) for p in pages]) if pages else 0
    render_blocking_resources = sum(1 for p in pages if int(getattr(p, 'stylesheets', 0) or 0) > 0)

    resp_times = [int(getattr(p, 'response_ms', 0) or 0) for p in pages if getattr(p, 'response_ms', None) is not None]
    avg_resp_ms = int(mean(resp_times)) if resp_times else 0

    def _is_unminified(url: str) -> bool:
        url = (url or '').lower()
        return (url.endswith('.css') or url.endswith('.js')) and '.min.' not in url

    unmin_css = sum(1 for p in pages for href in (getattr(p, 'stylesheets_href', []) or []) if _is_unminified(href))
    unmin_js = sum(1 for p in pages for src in (getattr(p, 'scripts_src', []) or []) if _is_unminified(src))

    origin_host = urlparse(getattr(cr, 'seed', '') or '').hostname or ''
    def _host(u: str) -> str:
        try:
            return urlparse(u or '').hostname or ''
        except Exception:
            return ''

    third_party_scripts = sum(
        1 for p in pages for src in (getattr(p, 'scripts_src', []) or [])
        if origin_host and _host(src) and _host(src) != origin_host
    )

    def _compressed(headers: Dict[str, str]) -> bool:
        enc = (headers or {}).get('Content-Encoding', '').lower()
        return ('gzip' in enc) or ('br' in enc) or ('deflate' in enc)

    missing_compression = sum(1 for p in pages if not _compressed(getattr(p, 'headers', {}) or {}))

    # Lazy loading images
    def _has_lazy(attrs: Dict[str, Any]) -> bool:
        val = str((attrs or {}).get('loading', '')).lower()
        return val == 'lazy'

    lazy_issues = 0
    for p in pages:
        images = getattr(p, 'images', []) or []
        for img in images:
            attrs = img.get('attrs', {}) if isinstance(img, dict) else getattr(img, 'attrs', {})
            if not _has_lazy(attrs):
                lazy_issues += 1

    # OPTIONAL Lighthouse lab metrics (Core Web Vitals)
    lcp = fcp = cls = tbt = fid = si = tti = dcl = 0
    if os.getenv("ENABLE_LIGHTHOUSE", "0") == "1" and total_pages > 0:
        try:
            cmd = ["lighthouse", cr.seed, "--quiet", "--output=json", "--chrome-flags=--headless"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=int(os.getenv("LIGHTHOUSE_TIMEOUT", "90")))
            if proc.returncode == 0 and proc.stdout:
                lh = json.loads(proc.stdout)
                audits = lh.get("audits", {})
                def _val(key):
                    a = audits.get(key, {})
                    return a.get("numericValue") or a.get("score") or 0
                lcp = _val("largest-contentful-paint")
                fcp = _val("first-contentful-paint")
                cls = _val("cumulative-layout-shift")
                tbt = _val("total-blocking-time")
                si  = _val("speed-index")
                tti = _val("interactive")
                dcl = _val("dom-content-loaded")
                fid = 0  # field value typically; keep 0 unless measured
        except Exception:
            pass

    # Requests per page now includes images (approx)
    metrics.update({
        "76.Largest Contentful Paint (LCP)": lcp,
        "77.First Contentful Paint (FCP)": fcp,
        "78.Cumulative Layout Shift (CLS)": cls,
        "79.Total Blocking Time": tbt,
        "80.First Input Delay": fid,
        "81.Speed Index": si,
        "82.Time to Interactive": tti,
        "83.DOM Content Loaded": dcl,
        "84.Total Page Size": int(avg_page_size),  # bytes/page
        "85.Requests Per Page": float(avg_scripts + avg_styles + avg_images + 1),
        "86.Unminified CSS": unmin_css,
        "87.Unminified JavaScript": unmin_js,
        "88.Render Blocking Resources": render_blocking_resources,
        "89.Excessive DOM Size": sum(1 for p in pages if int(getattr(p, 'dom_nodes_est', 0) or 0) > 1500),
        "90.Third-Party Script Load": third_party_scripts,
        "91.Server Response Time": avg_resp_ms,
        "92.Image Optimization": 0,
        "93.Lazy Loading Issues": lazy_issues,
        "94.Browser Caching Issues": _count_missing_cache_headers(pages),
        "95.Missing GZIP / Brotli": missing_compression,
        "96.Resource Load Errors": len(getattr(cr, 'errors', []) or []),
    })

    # ---- Additional basics
    metrics["97.Mobile Friendly Test"] = 0
    viewport_yes = sum(1 for p in pages if bool(getattr(p, 'viewport_meta', False)))
    metrics["98.Viewport Meta Tag"] = viewport_yes

    metrics["105.HTTPS Implementation"] = sum(1 for p in pages if str(getattr(p, 'url', '') or '').startswith('https://'))
    metrics["108.Mixed Content"] = sum(int(getattr(p, 'mixed_content_http', 0) or 0) for p in pages)

    metrics["136.Sitemap Presence"] = 1 if sitemap_list else 0
    metrics["137.Noindex Issues"] = meta_noindex_count

    metrics["168.Total Broken Links"] = metrics["27.Broken Internal Links"] + metrics["28.Broken External Links"]
    metrics["169.Internal Broken Links"] = metrics["27.Broken Internal Links"]
    metrics["170.External Broken Links"] = metrics["28.Broken External Links"]
    metrics["173.Status Code Distribution"] = {str(k): int(v) for k, v in status_bucket.items()}

    # ---- Fill placeholder IDs with 0 (no empties)
    for i in list(range(99, 105)) + list(range(106, 136)) + list(range(138, 167)) + list(range(171, 180)) + list(range(181, 201)):
        key = f"{i}.Placeholder"
        if key not in metrics:
            metrics[key] = 0

    # Ensure no None values AND scalarize dicts/lists for table rendering
    def _finalize_values(d: Dict[str, Any]) -> None:
        for k, v in list(d.items()):
            if v is None:
                d[k] = 0 if not k.endswith("Distribution") else {}
            # If UI expects scalar values, stringify known dicts
            if isinstance(v, dict):
                # keep charts-friendly originals in details, but stringify for table value
                details[k] = v
                d[k] = json.dumps(v, ensure_ascii=False)
            elif isinstance(v, (list, set, tuple)):
                d[k] = len(v)

    _finalize_values(metrics)

    # Store useful aggregates for scoring and UI
    details["total_images"] = total_images
    details["total_images_missing_alt"] = total_images_missing_alt

    return {"metrics": metrics, "details": details}

def _count_missing_cache_headers(pages: List[PageLike]) -> int:
    count = 0
    for p in pages:
        headers = getattr(p, 'headers', {}) or {}
        cc = (headers.get('Cache-Control') or headers.get('cache-control') or '').lower()
        if not cc:
            count += 1
        else:
            m = re.search(r'max-age=(\d+)', cc)
            if not m:
                count += 1
            else:
                try:
                    if int(m.group(1)) < 60:
                        count += 1
                except Exception:
                    count += 1
    return count
``
