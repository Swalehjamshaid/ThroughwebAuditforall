
import os, requests

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

def fetch_pagespeed(url: str, strategy: str = 'mobile', api_key: str | None = None):
    """
    Returns dict with lighthouse categories (0..100) and core web vitals (field+lab) if available.
    strategy: 'mobile' or 'desktop'
    """
    params = {
        'url': url,
        'strategy': strategy,
        'category': ['PERFORMANCE','ACCESSIBILITY','BEST_PRACTICES','SEO'],
        # You can also include 'PWA' if relevant
    }
    if api_key:
        params['key'] = api_key

    r = requests.get(PSI_ENDPOINT, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()

    lh = data.get('lighthouseResult', {})
    cats = lh.get('categories', {})

    # Lighthouse category scores are 0..1; convert to 0..100 for clarity
    cat_scores = {
        'Performance & Web Vitals': round((cats.get('performance', {}).get('score', 0) or 0) * 100, 1),
        'Accessibility': round((cats.get('accessibility', {}).get('score', 0) or 0) * 100, 1),
        'Best Practices': round((cats.get('best-practices', {}).get('score', 0) or cats.get('best_practices', {}).get('score', 0) or 0) * 100, 1),
        'SEO': round((cats.get('seo', {}).get('score', 0) or 0) * 100, 1),
    }

    # Field data (CrUX) can be in loadingExperience or originLoadingExperience
    loading = data.get('loadingExperience') or {}
    origin = data.get('originLoadingExperience') or {}
    # Prefer page; if insufficient, origin_fallback is often flagged in loadingExperience
    chosen = loading if loading.get('metrics') else origin

    metrics = (chosen or {}).get('metrics', {})  # may be empty
    # keys: LARGEST_CONTENTFUL_PAINT_MS, INTERACTION_TO_NEXT_PAINT, CUMULATIVE_LAYOUT_SHIFT_SCORE, FIRST_CONTENTFUL_PAINT_MS, EXPERIMENTAL_TIME_TO_FIRST_BYTE
    field_vitals = {
        'LCP_ms_p75': (metrics.get('LARGEST_CONTENTFUL_PAINT_MS', {}).get('percentile')),
        'INP_ms_p75': (metrics.get('INTERACTION_TO_NEXT_PAINT', {}).get('percentile')),
        'CLS_p75': (metrics.get('CUMULATIVE_LAYOUT_SHIFT_SCORE', {}).get('percentile')),
        'FCP_ms_p75': (metrics.get('FIRST_CONTENTFUL_PAINT_MS', {}).get('percentile')),
        'TTFB_ms_p75': (metrics.get('EXPERIMENTAL_TIME_TO_FIRST_BYTE', {}).get('percentile')),
        'source': 'page' if loading.get('metrics') else 'origin',
    }

    # Lab vitals from Lighthouse audits (best-effort)
    audits = lh.get('audits', {})
    lab_vitals = {
        'FCP_ms': audits.get('first-contentful-paint', {}).get('numericValue'),
        'LCP_ms': audits.get('largest-contentful-paint', {}).get('numericValue'),
        'CLS': audits.get('cumulative-layout-shift', {}).get('numericValue'),
        'INP_ms': audits.get('experimental-interaction-to-next-paint', {}).get('numericValue') or audits.get('interaction-to-next-paint', {}).get('numericValue'),
        'TTFB_ms': audits.get('server-response-time', {}).get('numericValue'),
    }

    return {
        'categories': cat_scores,
        'field_vitals': field_vitals,
        'lab_vitals': lab_vitals,
        'analysisUTCTimestamp': data.get('analysisUTCTimestamp'),
        'strategy': strategy,
    }
``
