from typing import Dict

def compute_overall(category_scores: Dict[str, int]) -> int:
    # Weighted average: Performance 30%, SEO 20%, Accessibility 20%, Best Practices 15%, Security 15%
    weights = {"Performance": 0.3, "SEO": 0.2, "Accessibility": 0.2, "Best Practices": 0.15, "Security": 0.15}
    return int(sum(category_scores.get(k, 0) * w for k, w in weights.items()))


def grade_from_score(score: int) -> str:
    if score >= 92: return 'A+'
    if score >= 85: return 'A'
    if score >= 78: return 'B+'
    if score >= 70: return 'B'
    if score >= 62: return 'C'
    if score >= 50: return 'D'
    return 'E'


def summarize_200_words(url: str, category_scores: Dict[str,int], issues: list) -> str:
    note = (
        f"We audited {url} across performance, SEO, accessibility, best practices, and security. "
        f"Strong areas: " + ", ".join([k for k,v in sorted(category_scores.items(), key=lambda x: -x[1])[:2]]) + ". "
        f"Top improvement items: " + ", ".join(issues[:3]) + ". "
        "Addressing these will improve Core UX, ranking signals, and resilience."
    )
    return note
