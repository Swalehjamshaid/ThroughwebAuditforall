
import requests

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

def fetch_pagespeed(url: str, strategy: str = 'mobile', api_key: str | None = None):
    """
    Fetch PageSpeed Insights (Lighthouse + CrUX) data for a URL.
    Returns a dict containing:
      - categories: Lighthouse category scores (0..100)
      - field_vitals: p75 CrUX metrics (may use origin fallback)
      - lab_vitals: Lighthouse lab metrics
      - analysisUTCTimestamp: PSI run timestamp
      - strategy: 'mobile' or 'desktop'
    """
    if strategy not in ('mobile', 'desktop'):
        strategy = 'mobile'

    params = {
        'url': url,
        'strategy': strategy,
        'category': ['PERFORMANCE', 'ACCESSIBILITY', 'BEST_PRACTICES', 'SEO'],
    }
    if api_key:
        params['key'] = api_key

    resp = requests.get(PSI_ENDPOINT, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    lighthouse = data.get('lighthouseResult', {}) or {}
    cats = lighthouse.get('categories', {}) or {}

    categories_100 = {
        'Performance & Web Vitals': round((cats.get('performance', {}).get('score', 0) or 0) * 100, 1),
        'Accessibility': round((cats.get('accessibility', {}).get('score', 0) or 0) * 100, 1),
        'Best Practices': round((cats.get('best-practices', {}).get('score', 0)
                                 or cats.get('best_practices', {}).get('score', 0)
                                 or 0) * 100, 1),
        'SEO': round((cats.get('seo', {}).get('score', 0) or 0) * 100, 1),
    }

    loading = data.get('loadingExperience') or {}
    origin = data.get('originLoadingExperience') or {}
    chosen = loading if loading.get('metrics') else origin
    metrics = (chosen or {}).get('metrics', {}) or {}

    field_vitals = {
        'LCP_ms_p75': metrics.get('LARGEST_CONTENTFUL_PAINT_MS', {}).get('percentile'),
        'INP_ms_p75': metrics.get('INTERACTION_TO_NEXT_PAINT', {}).get('percentile'),
        'CLS_p75': metrics.get('CUMULATIVE_LAYOUT_SHIFT_SCORE', {}).get('percentile'),
        'FCP_ms_p75': metrics.get('FIRST_CONTENTFUL_PAINT_MS', {}).get('percentile'),
        'TTFB_ms_p75': metrics.get('EXPERIMENTAL_TIME_TO_FIRST_BYTE', {}).get('percentile'),
        'source': 'page' if loading.get('metrics') else 'origin',
    }

    audits = lighthouse.get('audits', {}) or {}
    lab_vitals = {
        'FCP_ms': audits.get('first-contentful-paint', {}).get('numericValue'),
        'LCP_ms': audits.get('largest-contentful-paint', {}).get('numericValue'),
        'CLS': audits.get('cumulative-layout-shift', {}).get('numericValue'),
        'INP_ms': audits.get('experimental-interaction-to-next-paint', {}).get('numericValue')
                  or audits.get('interaction-to-next-paint', {}).get('numericValue'),
        'TTFB_ms': audits.get('server-response-time', {}).get('numericValue'),
    }

    return {
        'categories': categories_100,
        'field_vitals': field_vitals,
        'lab_vitals': lab_vitals,
        'analysisUTCTimestamp': data.get('analysisUTCTimestamp'),
        'strategy': strategy,
    }
