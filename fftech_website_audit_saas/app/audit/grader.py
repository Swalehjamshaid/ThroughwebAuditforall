
from typing import Dict, List
CATEGORY_WEIGHTS = {
    'Overall Site Health': 0.10,
    'Crawlability & Indexation': 0.15,
    'On-Page SEO': 0.15,
    'Technical & Performance': 0.20,
    'Mobile & Usability': 0.10,
    'Security & HTTPS': 0.15,
    'International SEO': 0.05,
    'Backlinks & Authority': 0.05,
    'Advanced/Thematic': 0.03,
    'Trend/Historical': 0.02,
}

def grade_from_score(score: float) -> str:
    if score >= 95: return 'A+'
    if score >= 85: return 'A'
    if score >= 75: return 'B'
    if score >= 60: return 'C'
    return 'D'

def compute_overall(category_scores: Dict[str, float]) -> float:
    overall = 0.0
    for cat, s in category_scores.items():
        w = CATEGORY_WEIGHTS.get(cat, 0.0)
        overall += w * s
    return round(overall, 2)

def summarize_200_words(domain: str, category_scores: Dict[str,float], top_issues: List[str]) -> str:
    strengths = sorted([(c, s) for c, s in category_scores.items()], key=lambda x: x[1], reverse=True)[:3]
    weaknesses = sorted([(c, s) for c, s in category_scores.items()], key=lambda x: x[1])[:3]
    strengths_str = ", ".join([f"{c} ({int(s)}%)" for c, s in strengths])
    weaknesses_str = ", ".join([f"{c} ({int(s)}%)" for c, s in weaknesses])
    issues_str = "; ".join(top_issues[:5]) if top_issues else "No critical issues detected"
    text = (
        f"This certified audit evaluates {domain} across technical SEO, performance, security, mobile usability and international readiness. "
        f"The site demonstrates strong foundations in {strengths_str}, indicating well structured markup and consistent best practices. "
        f"However, opportunities exist in {weaknesses_str}, where targeted remediation will yield material improvements in search visibility, stability and user experience. "
        f"Priority actions include resolving: {issues_str}. "
        f"We recommend optimizing Core Web Vitals (LCP, CLS, TBT), enforcing comprehensive security headers (CSP, HSTS, X-Frame-Options), and consolidating canonical/redirect logic to minimize duplication and crawl waste. "
        f"Implement continuous monitoring via scheduled audits and track trend lines to validate progress. This report provides category scores, a strict grade and actionable guidance designed for executives, stakeholders and engineering teams."
    )
    return " ".join(text.split())
