
from urllib.parse import urlparse
from typing import Dict, Any, Tuple

# Build METRIC_DESCRIPTORS for IDs 1–200
METRIC_DESCRIPTORS: Dict[int, Dict[str, str]] = {}
sections = [
    ("Executive Summary & Grading", [
        "Overall Site Health Score (%)", "Website Grade (A+ to D)", "Executive Summary (200 Words)",
        "Strengths Highlight Panel", "Weak Areas Highlight Panel", "Priority Fixes Panel",
        "Visual Severity Indicators", "Category Score Breakdown", "Industry-Standard Presentation",
        "Print / Certified Export Readiness"
    ]),
    ("Overall Site Health", ["Site Health Score", "Total Errors", "Total Warnings", "Total Notices", "Total Crawled Pages",
                              "Total Indexed Pages", "Issues Trend", "Crawl Budget Efficiency", "Orphan Pages Percentage", "Audit Completion Status"]),
    # Add remaining categories from your spec...
]
idx = 1
for category, items in sections:
    for name in items:
        METRIC_DESCRIPTORS[idx] = {"name": name, "category": category}
        idx += 1

# Scoring weights
WEIGHTS = {"security": 0.35, "performance": 0.25, "seo": 0.20, "mobile": 0.10, "content": 0.10}
SECURITY_PENALTIES = {"csp": 20, "hsts": 15, "x_frame": 10, "referrer_policy": 5}

def canonical_origin(url: str) -> str:
    u = urlparse(url)
    return f"{u.scheme or 'https'}://{u.netloc}".lower()

def clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))

def grade_from_score(score: float) -> str:
    s = round(score)
    if s >= 90: return 'A'
    if s >= 80: return 'B'
    if s >= 70: return 'C'
    if s >= 60: return 'D'
    return 'F'

def compute_category_security(sec: Dict[str, Any]) -> float:
    base = 100 if sec.get('https_enabled') else 60
    for k, penalty in SECURITY_PENALTIES.items():
        if not sec.get(k, False):
            base -= penalty
    return clamp(base)

def compute_category_performance(perf: Dict[str, Any]) -> float:
    score = 100
    ttfb = perf.get('ttfb_ms', 0)
    size = perf.get('payload_kb', 0)
    if ttfb > 800: score -= 25
    if size > 1500: score -= 25
    return clamp(score)

def aggregate_score(metrics: Dict[str, Dict[str, Any]]) -> Tuple[float, Dict[str, float]]:
    cats = {
        "security": compute_category_security(metrics.get('security', {})),
        "performance": compute_category_performance(metrics.get('performance', {})),
        "seo": 70, "mobile": 80, "content": 75
    }
    total = sum(WEIGHTS[k] * cats[k] for k in WEIGHTS.keys())
    return round(clamp(total), 1), cats
