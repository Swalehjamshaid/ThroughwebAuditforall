
"""Scoring framework: computes per-category and overall grades.
Flexible weighting; produces A+..D grading.
"""
from __future__ import annotations
from typing import Dict, Any, Tuple

CATEGORY_WEIGHTS = {
    'Executive Summary': 0.10,
    'Overall Health': 0.20,
    'Crawlability & Indexation': 0.20,
    'On-Page SEO': 0.20,
    'Performance & Technical': 0.15,
    'Mobile, Security & Intl': 0.10,
    'Competitor Analysis': 0.03,
    'Broken Links Intelligence': 0.01,
    'Opportunities, Growth & ROI': 0.01,
}

# Map numeric score [0..100] to letter grade

def grade_from_score(score: float) -> str:
    if score >= 97: return 'A+'
    if score >= 90: return 'A'
    if score >= 85: return 'A-'
    if score >= 80: return 'B+'
    if score >= 75: return 'B'
    if score >= 70: return 'B-'
    if score >= 65: return 'C+'
    if score >= 60: return 'C'
    if score >= 55: return 'C-'
    if score >= 50: return 'D+'
    return 'D'


def normalize(value: float | int | None, min_v=0.0, max_v=100.0) -> float:
    if value is None: return 0.0
    try:
        v = float(value)
    except Exception: return 0.0
    if v < min_v: v = min_v
    if v > max_v: v = max_v
    return 100.0 * (v - min_v) / (max_v - min_v) if max_v > min_v else 0.0


def compute_category_scores(metrics: Dict[str, Any]) -> Dict[str, float]:
    """Compute category scores using a few representative signals.
    Extend mappings as you implement more metrics.
    """
    cats: Dict[str, float] = {}

    # Overall Health
    overall = 0.0
    overall += normalize(100 - float(metrics.get('total_errors', 0)), 0, 100) * 0.4
    overall += normalize(100 - float(metrics.get('total_warnings', 0)), 0, 100) * 0.2
    overall += normalize(float(metrics.get('total_indexed_pages', 0)), 0, max(1.0, float(metrics.get('total_crawled_pages', 1)))) * 0.2
    overall += normalize(100 - float(metrics.get('orphan_pages_percent', 0)), 0, 100) * 0.2
    cats['Overall Health'] = overall

    # Performance & Technical – use core web vitals if present
    perf = 0.0
    # Ideal lower numbers -> higher score
    def invert(v: float, best: float, worst: float) -> float:
        return normalize(worst - v, worst - best, worst)
    lcp = float(metrics.get('lcp', 4.0))
    cls = float(metrics.get('cls', 0.25))
    tbt = float(metrics.get('total_blocking_time', 600))
    perf += invert(lcp, 2.5, 6.0) * 0.4
    perf += invert(cls, 0.1, 0.35) * 0.2
    perf += invert(tbt, 200, 800) * 0.4
    cats['Performance & Technical'] = perf

    # On-Page SEO – basic coverage
    seo = 0.0
    missing_titles = float(metrics.get('missing_title_tags', 0))
    missing_meta = float(metrics.get('missing_meta_descriptions', 0))
    missing_h1 = float(metrics.get('missing_h1', 0))
    total_pages = float(metrics.get('total_crawled_pages', 1))
    seo += normalize(100 - (100 * missing_titles / max(1.0, total_pages)), 0, 100) * 0.4
    seo += normalize(100 - (100 * missing_meta / max(1.0, total_pages)), 0, 100) * 0.3
    seo += normalize(100 - (100 * missing_h1 / max(1.0, total_pages)), 0, 100) * 0.3
    cats['On-Page SEO'] = seo

    # Crawlability & Indexation – http status distribution
    crawl = 0.0
    http2xx = float(metrics.get('http_2xx_pages', 0))
    total = http2xx + float(metrics.get('http_3xx_pages', 0)) + float(metrics.get('http_4xx_pages', 0)) + float(metrics.get('http_5xx_pages', 0))
    good_ratio = (http2xx / max(1.0, total)) * 100.0
    crawl += normalize(good_ratio, 0, 100)
    cats['Crawlability & Indexation'] = crawl

    # Simple placeholders for remaining categories
    cats['Executive Summary'] = (cats['Overall Health'] + cats['On-Page SEO'] + cats['Performance & Technical']) / 3.0
    cats['Mobile, Security & Intl'] = cats['Performance & Technical'] * 0.8
    cats['Competitor Analysis'] = 60.0
    cats['Broken Links Intelligence'] = normalize(100 - float(metrics.get('total_broken_links', 0)), 0, 100)
    cats['Opportunities, Growth & ROI'] = 65.0

    return cats


def compute_overall_score(category_scores: Dict[str, float]) -> Tuple[float, str]:
    s = 0.0
    for cat, val in category_scores.items():
        w = CATEGORY_WEIGHTS.get(cat, 0.0)
        s += w * val
    grade = grade_from_score(s)
    return s, grade

