
from typing import Dict

def overall_score(category_scores: Dict[str, float]) -> float:
    if not category_scores:
        return 0.0
    return sum(category_scores.values()) / len(category_scores)


def to_grade(score: float) -> str:
    if score >= 90: return "A+"
    if score >= 80: return "A"
    if score >= 70: return "B"
    if score >= 60: return "C"
    if score >= 50: return "D"
    return "F"
