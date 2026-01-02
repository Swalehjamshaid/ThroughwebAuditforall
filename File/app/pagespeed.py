
"""
Robust Google PageSpeed Insights client with:
- API key support (recommended for automated queries)
- Exponential backoff with jitter and Retry-After handling on HTTP 429
- File-based caching to reduce repeated calls
- Cross-process file lock to serialize PSI calls across multiple Gunicorn workers

Outputs category scores with keys your templates expect:
'Performance &amp; Web Vitals', 'Accessibility', 'Best Practices', 'SEO'
"""
from __future__ import annotations

import os
import time
import json
import random
import fcntl
import logging
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlencode
from email.utils import parsedate_to_datetime

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

# --- Hard-coded API key fallback (as requested) ---
HARDCODED_API_KEY = "AIzaSyDUVptDEm1ZbiBdb5m1DGjvKCW_LBVJMEw"

# PSI categories to request (lowercase for API)
PSI_CATEGORIES = ["performance", "accessibility", "best-practices", "seo"]

# Output category keys (HTML-escaped names used in your templates)
OUTPUT_KEYS = {
    "performance": "Performance &amp; Web Vitals",
    "accessibility": "Accessibility",
    "best-practices": "Best Practices",
    "seo": "SEO",
}

# Cache & lock
CACHE_DIR = Path("/app/.psi_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOCK_FILE_PATH = Path("/app/.psi_lock")
LOCK_FILE_PATH.touch(exist_ok=True)


def _cache_key(url: str, strategy: str) -> Path:
    digest = hashlib.sha256(f"{url}|{strategy}".encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def _read_cache(path: Path, ttl_seconds: int) -> Optional[Dict[str, Any]]:
    try:
        if path.exists():
            age = time.time() - path.stat().st_mtime
            if age <= ttl_seconds:
                with path.open("r", encoding="utf-8") as f:
                    return json.load(f)
    except Exception as e:
        logger.warning("PSI cache read failed: %s", e)
    return None


def _write_cache(path: Path, data: Dict[str, Any]) -> None:
    try:
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        tmp.replace(path)
    except Exception as e:
        logger.warning("PSI cache write failed: %s", e)


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    """Parse Retry-After header into seconds (supports seconds or HTTP-date)."""
    if not value:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(value)
        if dt is not None:
            return max(dt.timestamp() - time.time(), 0.0)
    except Exception:
        pass
    return None


def _transform_categories(ps_json: Dict[str, Any]) -> Dict[str, float]:
    """Convert PSI/lighthouse categories (score 0..1) to 0..100 with your output keys."""
    out = {}
    try:
        cats = (ps_json.get("lighthouseResult", {}) or {}).get("categories", {}) or {}
        for api_key, out_key in OUTPUT_KEYS.items():
            score_0_1 = (cats.get(api_key, {}) or {}).get("score", None)
            out[out_key] = round((float(score_0_1) * 100.0) if score_0_1 is not None else 0.0, 1)
    except Exception as e:
        logger.warning("Failed to transform PSI categories: %s", e)
    return out


def _request_psi(endpoint: str, session: requests.Session, headers: Dict[str, str],
                 max_retries: int, base_sleep: float) -> Dict[str, Any]:
    """Perform a PSI request with robust 429 handling and exponential backoff."""
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            resp = session.get(endpoint, headers=headers, timeout=60)
            if resp.status_code == 429:
                ra = _parse_retry_after(resp.headers.get("Retry-After"))
                wait = ra if ra is not None else base_sleep * (2 ** attempt)
                jitter = random.uniform(0, 0.5 * base_sleep)
                wait = min(wait + jitter, 60.0)
                logger.warning("PSI 429 rate-limited; attempt=%d, wait=%.2fs", attempt + 1, wait)
                time.sleep(max(wait, 0.5))
                continue

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.RequestException as e:
            last_exc = e
            wait = min(base_sleep * (2 ** attempt), 30.0)
            logger.warning("PSI request error: %s; retrying in %.2fs", e, wait)
            time.sleep(wait)

    if last_exc:
        logger.error("PSI request failed after retries: %s", last_exc)
    raise last_exc if last_exc else RuntimeError("PSI request failed without exception")


def fetch_pagespeed(
    url: str,
    strategy: str = "mobile",
    api_key: Optional[str] = None,
    ttl_seconds: int = 6 * 3600,
    max_retries: int = 5,
    base_sleep: float = 1.0,
) -> Dict[str, Any]:
    """
    Public function used by main.py.
    Returns:
    {
        'categories': {
            'Performance &amp; Web Vitals': 87.0,
            'Accessibility': 92.0,
            'Best Practices': 90.0,
            'SEO': 85.0
        },
        'raw': <full PSI JSON>
    }
    """
    # Fallback to hard-coded key if none provided
    if not api_key:
        api_key = HARDCODED_API_KEY

    cache_path = _cache_key(url, strategy)
    cached = _read_cache(cache_path, ttl_seconds)
    if cached:
        return cached

    params = [("url", url), ("strategy", strategy)]
    for c in PSI_CATEGORIES:
        params.append(("category", c))
    if api_key:
        params.append(("key", api_key))
    endpoint = f"{BASE_URL}?{urlencode(params)}"

    # Serialize across workers to avoid per-minute bursts
    with LOCK_FILE_PATH.open("r+") as lockfile:
        fcntl.flock(lockfile, fcntl.LOCK_EX)
        try:
            session = requests.Session()
            headers = {"User-Agent": "CompHPK-Audit/1.0 (+PSI)"}

            raw_json = _request_psi(
                endpoint=endpoint,
                session=session,
                headers=headers,
                max_retries=max_retries,
                base_sleep=base_sleep
            )
            categories = _transform_categories(raw_json)
            data = {"categories": categories, "raw": raw_json}
            _write_cache(cache_path, data)
            return data
        finally:
            fcntl.flock(lockfile, fcntl.LOCK_UN)
