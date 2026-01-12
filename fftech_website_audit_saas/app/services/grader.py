
from __future__ import annotations
from typing import Dict, Tuple

GRADE_BANDS = [
    (95, "A+"),
    (88, "A"),
    (78, "B"),
    (66, "C"),
    (0,  "D"),
]

CATEGORY_WEIGHTS = {
    "A": 0.15,
    "B": 0.15,
    "C": 0.20,
    "D": 0.20,
    "E": 0.15,
    "F": 0.10,
    "G": 0.03,
    "H": 0.01,
    "I": 0.01,
}

def compute_overall_grade(category_scores: Dict[str, float]) -> Tuple[int, str]:
    total = 0.0
    for cat, score in category_scores.items():
        total += score * CATEGORY_WEIGHTS.get(cat, 0.0)
    overall = round(total)
    for threshold, grade in GRADE_BANDS:
        if overall >= threshold:
            return overall, grade
    return overall, "D"
