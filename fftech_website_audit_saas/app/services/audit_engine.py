
"""Audit Engine: fetches a site and computes metrics.
This is designed to be extensible; in production, use httpx/Playwright/Lighthouse APIs.
"""
from __future__ import annotations
from typing import Dict, Any

import asyncio

try:
    import httpx
    from bs4 import BeautifulSoup  # type: ignore
except Exception:
    httpx = None
    BeautifulSoup = None


async def fetch_html(url: str) -> str:
    if httpx is None:
        return ''
    timeout = httpx.Timeout(20.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text


async def compute_basic_metrics(url: str) -> Dict[str, Any]:
    """Compute a minimal set of metrics from HTML; extend with more checks."""
    html = ''
    try:
        html = await fetch_html(url)
    except Exception:
        html = ''
    metrics: Dict[str, Any] = {
        'total_crawled_pages': 1,
        'total_indexed_pages': 1,
        'http_2xx_pages': 1,
        'http_3xx_pages': 0,
        'http_4xx_pages': 0,
        'http_5xx_pages': 0,
        'total_errors': 0,
        'total_warnings': 0,
        'orphan_pages_percent': 0,
        'lcp': 4.0,
        'cls': 0.25,
        'total_blocking_time': 600,
        'missing_title_tags': 0,
        'missing_meta_descriptions': 0,
        'missing_h1': 0,
        'total_broken_links': 0,
    }
    if not html or BeautifulSoup is None:
        return metrics

    soup = BeautifulSoup(html, 'html.parser')
    title = soup.find('title')
    h1 = soup.find('h1')
    meta_desc = soup.find('meta', attrs={'name': 'description'})

    metrics['missing_title_tags'] = 0 if title else 1
    metrics['missing_h1'] = 0 if h1 else 1
    metrics['missing_meta_descriptions'] = 0 if meta_desc else 1

    # Simple link check
    links = [a.get('href') for a in soup.find_all('a') if a.get('href')]
    metrics['total_broken_links'] = 0  # Placeholder: resolve & test status in production

    return metrics


async def run_audit(url: str) -> Dict[str, Any]:
    return await compute_basic_metrics(url)

