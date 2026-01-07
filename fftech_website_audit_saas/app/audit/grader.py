from typing import Dict, List

GRADE_SCALE = [
    (90, 'A'), (80, 'B'), (70, 'C'), (60, 'D'), (0, 'F')
]

def compute_overall(category_scores: Dict[str, int]) -> float:
    vals = list(category_scores.values())
    return round(sum(vals)/len(vals), 1) if vals else 0.0

def grade_from_score(score: float) -> str:
    for cutoff, letter in GRADE_SCALE:
        if score >= cutoff:
            return letter
    return 'F'

def summarize_200_words(url: str, category_scores: Dict[str, int], top_issues: List[str]) -> str:
    parts = [
        f"We assessed {url} across Performance, Accessibility, SEO, and Security.",
        "Scores were: " + ", ".join([f"{k}: {v}/100" for k, v in category_scores.items()]) + ".",
    ]
    if top_issues:
        parts.append("Top issues: " + ", ".join(top_issues) + ".")
    else:
        parts.append("No critical issues were detected during the basic audit.")
    parts.append("Focus on HTTPS, metadata quality, and alt text for accessibility. Improve performance by minimizing payloads and enabling compression and caching.")
    txt = " ".join(parts)
    return txt[:1200]
