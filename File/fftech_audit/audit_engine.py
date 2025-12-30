
# fftech_audit/audit_engine.py (improved)
from __future__ import annotations
import datetime as dt
from typing import Dict, Any
from statistics import mean
from fftech_audit.crawlers import crawl_site
from fftech_audit.analyzers import summarize_crawl

# ------------------ Public API ------------------

def _grade_from_score(score: float) -> str:
    if score >= 95: return "A+"
    if score >= 85: return "A"
    if score >= 75: return "B"
    if score >= 65: return "C"
    if score >= 55: return "D"
    return "F"

def run_audit(url: str) -> Dict[str, Any]:
    """
    Executes site crawl + analyzers, computes category scores, overall,
    and returns a rich metrics dict with NO empty values.
    """
    cr = crawl_site(url)
    res = summarize_crawl(cr)
    m = res["metrics"]

    # Category scores
    score_perf = _score_performance(m)
    score_mobile = _score_mobile(m)
    score_a11y = _score_accessibility(m)
    score_security = _score_security(m)
    score_indexing = _score_indexing(m)
    score_metadata = _score_metadata(m)
    score_structure = _score_structure(m)

    weights = {
        "Performance": 0.22,
        "Mobile": 0.12,
        "Accessibility": 0.12,
        "Security": 0.15,
        "Indexing": 0.14,
        "Metadata": 0.12,
        "Structure": 0.13,
    }

    overall = (
        score_perf * weights["Performance"] +
        score_mobile * weights["Mobile"] +
        score_a11y * weights["Accessibility"] +
        score_security * weights["Security"] +
        score_indexing * weights["Indexing"] +
        score_metadata * weights["Metadata"] +
        score_structure * weights["Structure"]
    )

    category_breakdown = {
        "Performance": round(score_perf, 1),
        "Mobile": round(score_mobile, 1),
        "Accessibility": round(score_a11y, 1),
        "Security": round(score_security, 1),
        "Indexing": round(score_indexing, 1),
        "Metadata": round(score_metadata, 1),
        "Structure": round(score_structure, 1),
    }

    strengths, weaknesses, fixes = _summarize_strengths_weaknesses(m, category_breakdown)
    exec_summary = _generate_exec_summary(url, category_breakdown, strengths, weaknesses, fixes)

    # Final metrics dict: ensure site health score populated and no empty fields
    out_metrics: Dict[str, Any] = {
        "target.url": url,
        "generated_at": dt.datetime.utcnow().isoformat(),
        "overall.health_score": round(overall, 1),
        "overall.grade": _grade_from_score(overall),
        "summary.strengths": strengths,
        "summary.weaknesses": weaknesses,
        "summary.priority_fixes": fixes,
        "summary.category_breakdown": category_breakdown,
        "summary.executive": exec_summary,
        **m,
    }

    # Mirror overall into metric 11 for table visibility
    out_metrics["11.Site Health Score"] = round(overall, 1)

    # Charts
    charts = {
        "status_distribution": out_metrics.get("173.Status Code Distribution", {}),
    }

    return {
        "metrics": out_metrics,
        "category_breakdown": category_breakdown,
        "charts": charts,
    }

# ------------------ Scoring helpers ------------------
def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))

def _safe_total(m: Dict[str, Any]) -> float:
    t = float(m.get("15.Total Crawled Pages") or 0)
    return t if t > 0 else 1

def _score_performance(m: Dict[str, Any]) -> float:
    # Use per-page averages to avoid penalizing larger crawls
    size_bytes = float(m.get("84.Total Page Size") or 0)  # avg per page
    req = float(m.get("85.Requests Per Page") or 1)
    rbr_pages = float(m.get("88.Render Blocking Resources") or 0)
    big_dom_pages = float(m.get("89.Excessive DOM Size") or 0)
    total = _safe_total(m)

    rbr_ratio = rbr_pages / total
    big_dom_ratio = big_dom_pages / total

    penalties = 0.0
    if size_bytes > 2_000_000: penalties += 20  # >2MB avg/page
    elif size_bytes > 1_000_000: penalties += 10

    if req > 60: penalties += 20
    elif req > 40: penalties += 10

    penalties += rbr_ratio * 25
    penalties += big_dom_ratio * 20

    base = 95.0
    return _clamp(base - penalties)

def _score_mobile(m: Dict[str, Any]) -> float:
    viewport_yes = float(m.get("98.Viewport Meta Tag") or 0)
    total_pages = _safe_total(m)
    ratio = viewport_yes / total_pages
    # Mobile friendliness (test not run) keeps baseline moderate
    baseline = 55.0
    return _clamp(baseline + 45.0 * ratio)

def _score_accessibility(m: Dict[str, Any]) -> float:
    missing_alt = float(m.get("55.Missing Image Alt Tags") or 0)
    # Estimate total images via alt missing + a small constant to avoid division by zero
    total_images_est = max(missing_alt + 5, 1)
    miss_ratio = missing_alt / total_images_est
    penalties = miss_ratio * 60
    base = 90.0
    return _clamp(base - penalties)

def _score_security(m: Dict[str, Any]) -> float:
    https_impl = float(m.get("105.HTTPS Implementation") or 0)
    mixed = float(m.get("108.Mixed Content") or 0)
    total_pages = _safe_total(m)
    https_ratio = https_impl / total_pages
    penalties = 0.0
    if https_ratio < 0.9: penalties += 20
    if https_ratio < 0.7: penalties += 35
    if mixed > 0: penalties += min(30.0, mixed * 3.0)
    base = 95.0
    return _clamp(base - penalties)

def _score_indexing(m: Dict[str, Any]) -> float:
    non_canonical = float(m.get("31.Non-Canonical Pages") or 0)
    missing_can = float(m.get("32.Missing Canonical Tags") or 0)
    meta_blocked = float(m.get("30.Meta Robots Blocked URLs") or 0)
    total = _safe_total(m)
    ratio = (non_canonical + missing_can + meta_blocked) / total
    penalties = ratio * 100
    base = 95.0
    return _clamp(base - penalties)

def _score_metadata(m: Dict[str, Any]) -> float:
    missing_title = float(m.get("41.Missing Title Tags") or 0)
    missing_meta = float(m.get("45.Missing Meta Descriptions") or 0)
    too_long = float(m.get("47.Meta Too Long") or 0)
    too_short = float(m.get("48.Meta Too Short") or 0)
    total = _safe_total(m)
    miss_ratio = (missing_title + missing_meta) / total
    length_issues = (too_long + too_short) / total
    penalties = miss_ratio * 60 + length_issues * 20
    base = 90.0
    return _clamp(base - penalties)

def _score_structure(m: Dict[str, Any]) -> float:
    missing_h1 = float(m.get("49.Missing H1") or 0)
    multiple_h1 = float(m.get("50.Multiple H1") or 0)
    non_seo_urls = float(m.get("65.Non-SEO-Friendly URLs") or 0)
    total = _safe_total(m)
    ratio = (missing_h1 + multiple_h1 + non_seo_urls) / total
    penalties = ratio * 100
    base = 90.0
    return _clamp(base - penalties)


# ------------------ Narrative helpers ------------------
def _summarize_strengths_weaknesses(m: Dict[str, Any], cb: Dict[str, float]):
    strengths, weaknesses, fixes = [], [], []
    for k, v in cb.items():
        if v >= 80:
            strengths.append(f"{k} is strong ({v:.0f}%).")
    for k, v in cb.items():
        if v < 60:
            weaknesses.append(f"{k} below target ({v:.0f}%).")

    # Priority fixes
    if (m.get("74.Broken External Links", 0) or 0) > 0 or (m.get("27.Broken Internal Links", 0) or 0) > 0:
        fixes.append("Resolve broken internal/external links to recover link equity and UX.")
    if (m.get("45.Missing Meta Descriptions", 0) or 0) > 0 or (m.get("41.Missing Title Tags", 0) or 0) > 0:
        fixes.append("Complete title & meta descriptions; enforce length and uniqueness.")
    if (m.get("32.Missing Canonical Tags", 0) or 0) > 0 or (m.get("31.Non-Canonical Pages", 0) or 0) > 0:
        fixes.append("Fix canonical implementation to consolidate signals.")
    if (m.get("98.Viewport Meta Tag", 0) or 0) == 0:
        fixes.append("Add responsive viewport meta for mobile friendliness.")
    if not fixes:
        fixes.append("Maintain current performance; monitor periodic changes and trends.")
    return strengths, weaknesses, fixes

def _generate_exec_summary(url: str, cb: Dict[str, float], strengths: list, weaknesses: list, fixes: list) -> str:
    parts = []
    parts.append(f"This report audits {url} across seven dimensions—Performance, Mobile, Accessibility, Security, Indexing, Metadata, and Structure—to produce an overall executive score.")
    parts.append("Category scores: " + ", ".join([f"{k} {v:.0f}%" for k, v in cb.items()]) + ".")
    if strengths:
        parts.append("Strengths: " + "; ".join(strengths) + ".")
    if weaknesses:
        parts.append("Weaknesses: " + "; ".join(weaknesses) + ".")
    parts.append("Priority actions: " + "; ".join(fixes) + ".")
    parts.append("Scores are derived from transparent heuristics (avg page size, request counts, canonical/meta/alt coverage, HTTPS/mixed content) and can be extended with Core Web Vitals and backlink authority in future iterations.")
    return " ".join(parts)
