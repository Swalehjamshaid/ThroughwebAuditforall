from typing import Dict

def compute_overall(category_scores: Dict[str, int]) -> int:
    if not category_scores:
        return 0
    return int(sum(category_scores.values()) / len(category_scores))


def grade_from_score(score: int) -> str:
    if score >= 90: return 'A+'
    if score >= 85: return 'A'
    if score >= 80: return 'B+'
    if score >= 70: return 'B'
    if score >= 60: return 'C'
    return 'D'


def summarize_200_words(url: str, category_scores: Dict[str,int], issues: list) -> str:
    parts = [
        f"We audited {url} for performance, SEO, accessibility, best practices, and security.",
        "Key improvement ideas include: " + ", ".join(issues[:3]) + ".",
        "Scores indicate overall health in the '" + str(int(sum(category_scores.values())/len(category_scores))) + "' range.",
        "Focus on optimizing assets, improving server response, and ensuring accessibility compliance for better user experience and rankings."
    ]
    return " ".join(parts)
