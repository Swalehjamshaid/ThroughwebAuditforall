def compute_overall(category_scores: dict) -> int:
    if not category_scores:
        return 0
    vals = [int(v) for v in category_scores.values()]
    return round(sum(vals)/len(vals))

def grade_from_score(score: int) -> str:
    if score >= 90: return 'A+'
    if score >= 85: return 'A'
    if score >= 75: return 'B'
    if score >= 65: return 'C'
    if score >= 50: return 'D'
    return 'F'

def summarize_200_words(url: str, category_scores: dict, top_issues: list) -> str:
    parts = [
        f"Audit Summary for {url}",
        f"Overall score derived from {len(category_scores)} categories.",
    ]
    if top_issues:
        parts.append("Top issues: " + ", ".join(top_issues[:5]))
    else:
        parts.append("No major issues detected in heuristic run.")
    return " ".join(parts)
