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
    pagina...(truncated 10556 characters)...mization": 0,
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
