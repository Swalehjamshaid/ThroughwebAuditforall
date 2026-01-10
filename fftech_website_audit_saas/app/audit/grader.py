
# app/audit/grader.py

from typing import Dict, List, Any

def compute_overall(category_scores: Dict[str, Any]) -> int:
    """
    Compute overall percentage (0..100) from category scores dict.
    Ignores non-numeric values safely.
    """
    if not category_scores:
        return 0
    vals = []
    for v in category_scores.values():
        try:
            vals.append(int(v))
        except Exception:
            # tolerate strings like "85" or bad types
            try:
                vals.append(int(float(v)))
            except Exception:
                pass
    if not vals:
        return 0
    overall = round(sum(vals) / len(vals))
    return max(0, min(100, overall))

def grade_from_score(score: int) -> str:
    """
    Map overall score to a grade A+..D using common executive scales.
    """
    s = int(score)
    if s >= 95: return "A+"
    if s >= 90: return "A"
    if s >= 85: return "A-"
    if s >= 80: return "B+"
    if s >= 75: return "B"
    if s >= 70: return "B-"
    if s >= 65: return "C+"
    if s >= 60: return "C"
    if s >= 55: return "C-"
    return "D"

def _compose_summary(url: str, category_scores: Dict[str, Any], top_issues: List[str]) -> str:
    """
    Build ~200-word executive summary that highlights strengths, weaknesses, and priorities.
    Deterministic and safe; no external calls.
    """
    # Normalize
    url = (url or "").strip()
    cats = {str(k): int(v) if str(v).isdigit() else _to_int(v) for k, v in (category_scores or {}).items()}
    issues = top_issues or []

    # Strengths & gaps
    strengths = [k for k, v in cats.items() if (v or 0) >= 75]
    gaps      = [k for k, v in cats.items() if (v or 0) < 60]

    strengths_txt = ", ".join(strengths) if strengths else "core hygiene and stability"
    gaps_txt      = ", ".join(gaps) if gaps else "a few technical areas"

    issues_preview = ", ".join(issues[:6]) if issues else "no critical issues reported"

    overall = compute_overall(cats)
    grade   = grade_from_score(overall)

    # Compose ~200 words (approx; not strictly enforced)
    summary = (
        f"Executive Overview for {url}: The site demonstrates a solid foundation with an overall health of {overall}/100 "
        f"and a grade of {grade}. Strength areas include {strengths_txt}, indicating consistent attention to essential "
        f"best practices. That said, {gaps_txt} remain below target and should be prioritized to unlock quick lifts in "
        f"performance, search visibility, and resilience. The top items observed are: {issues_preview}. Addressing these "
        f"first will have disproportionate impact on user experience and crawl/index efficiency.\n\n"
        f"Recommendations: begin by enforcing modern security headers (e.g., HSTS, CSP), stabilizing core web vitals, "
        f"and resolving structural SEO flags (canonicalization, metadata, internal link routing). For performance, reduce "
        f"render-blocking assets, optimize images, and leverage caching and compression. For SEO, standardize titles and "
        f"descriptions, strengthen headings, and ensure a comprehensive sitemap with robots allowing crawl of key templates. "
        f"Finally, re-run the audit after each change to verify measurable uplift and maintain certified reporting quality."
    )
    return summary

def summarize_200_words(*args, **kwargs) -> str:
    """
    Universal signature:
      - summarize_200_words(url, category_scores, top_issues)
      - summarize_200_words(context_dict)

    Returns a deterministic executive summary string (~200 words).
    """
    # 3-argument form
    if len(args) == 3 and isinstance(args[0], str) and isinstance(args[1], dict) and isinstance(args[2], (list, tuple)):
        url, category_scores, top_issues = args
        return _compose_summary(url, category_scores, list(top_issues))

    # 1-argument dict form
    if len(args) == 1 and isinstance(args[0], dict):
        ctx = args[0]
        url = ctx.get("url", "")
        category_scores = ctx.get("category_scores", {}) or {}
        top_issues = ctx.get("top_issues", []) or []
        return _compose_summary(url, category_scores, list(top_issues))

    # Fallback: try kwargs (url=..., category_scores=..., top_issues=...)
    url = kwargs.get("url", "")
    category_scores = kwargs.get("category_scores", {}) or {}
    top_issues = kwargs.get("top_issues", []) or []
    return _compose_summary(url, category_scores, list(top_issues))

# ---------- helpers ----------
def _to_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return 0
