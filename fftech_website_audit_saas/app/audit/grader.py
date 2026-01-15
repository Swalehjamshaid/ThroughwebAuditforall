
from typing import Dict

GRADE_BANDS = [
    (97, 'A+'), (93, 'A'), (90, 'A-'),
    (87, 'B+'), (83, 'B'), (80, 'B-'),
    (77, 'C+'), (73, 'C'), (70, 'C-'),
    (0, 'D')
]

def grade_from_score(score: float) -> str:
    for threshold, label in GRADE_BANDS:
        if score >= threshold:
            return label
    return 'D'

def compute_category_scores(results: Dict[str, Dict]):
    cat_scores = {}
    for cat, metrics in results.items():
        total_w = 0.0
        acc = 0.0
        for m in metrics.values():
            w = float(m.get('weight', 1.0))
            s = float(m.get('score', 0))
            acc += s * w
            total_w += w
        cat_scores[cat] = round(acc / total_w, 2) if total_w else 0.0
    overall = round(sum(cat_scores.values()) / max(len(cat_scores), 1), 2)
    return overall, cat_scores
