"""
grader.py
Backend grading and summary logic for AI Website Audit
"""

from typing import Dict, Tuple


def compute_overall(metrics: Dict[str, float]) -> float:
    """
    Compute overall score from metric dictionary
    """
    if not metrics:
        return 0.0

    valid_scores = [v for v in metrics.values() if isinstance(v, (int, float))]
    if not valid_scores:
        return 0.0

    return round(sum(valid_scores) / len(valid_scores), 2)


def grade_from_score(score: float) -> str:
    """
    Convert numeric score into grade
    """
    if score >= 90:
        return "A+"
    elif score >= 85:
        return "A"
    elif score >= 75:
        return "B+"
    elif score >= 65:
        return "B"
    elif score >= 55:
        return "C"
    elif score >= 45:
        return "D"
    else:
        return "F"


def score_breakdown(metrics: Dict[str, float]) -> Dict[str, str]:
    """
    Return grade per metric
    """
    return {k: grade_from_score(v) for k, v in metrics.items()}


def compute_weighted_score(
    metrics: Dict[str, float],
    weights: Dict[str, float]
) -> float:
    """
    Compute weighted score
    """
    total_weight = sum(weights.values())
    if total_weight == 0:
        return 0.0

    score = 0.0
    for key, value in metrics.items():
        weight = weights.get(key, 0)
        score += value * weight

    return round(score / total_weight, 2)


def summarize_200_words(report: Dict[str, float]) -> str:
    """
    Generate executive audit summary (approx 200 words)
    """
    overall = compute_overall(report)
    grade = grade_from_score(overall)

    summary = (
        f"This AI-powered website audit presents a comprehensive technical "
        f"and performance-based evaluation of the analyzed platform. "
        f"The overall score achieved is {overall}, corresponding to a grade of {grade}. "
        f"The assessment covers critical areas including SEO health, performance "
        f"efficiency, accessibility compliance, security posture, and adherence "
        f"to modern best practices.\n\n"
        f"Strong scores indicate effective optimization, stable architecture, "
        f"and readiness for scale, while lower scores highlight opportunities "
        f"for improvement in technical structure or content strategy. "
        f"This audit enables data-driven decision-making by identifying "
        f"optimization gaps, prioritizing corrective actions, and improving "
        f"user experience and search visibility.\n\n"
        f"By addressing the highlighted issues and maintaining best practices, "
        f"the website can significantly enhance reliability, engagement, "
        f"and long-term digital performance."
    )

    return summary
