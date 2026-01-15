from typing import Dict

WEIGHTS = {
    'executive': 0.10,
    'overall': 0.10,
    'crawlability': 0.20,
    'onpage': 0.25,
    'performance': 0.20,
    'mobile_security_intl': 0.10,
    'opportunities': 0.05,
}

def to_grade(score: float) -> str:
    if score >= 97: return 'A+'
    if score >= 93: return 'A'
    if score >= 90: return 'A-'
    if score >= 87: return 'B+'
    if score >= 83: return 'B'
    if score >= 80: return 'B-'
    if score >= 77: return 'C+'
    if score >= 73: return 'C'
    if score >= 70: return 'C-'
    if score >= 60: return 'D'
    return 'D'

def combine(category_scores: Dict[str, float]) -> float:
    total = 0.0
    for k,w in WEIGHTS.items():
        total += category_scores.get(k, 0.0) * w
    return round(total, 2)