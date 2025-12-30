
# fftech_audit/audit_engine.py
import datetime as dt
from typing import Dict, Any
from statistics import mean
from fftech_audit.crawlers import crawl_site
from fftech_audit.analyzers import summarize_crawl

def _grade_from_score(score: float) -> str:
    if score >= 90: return "A+"
    if score >= 80: return "A"
    if score >= 70: return "B"
    if score >= 60: return "C"
    if score >= 50: return "D"
    return "F"

def run_audit(url: str) -> Dict[str, Any]:
    """
    Executes site crawl + analyzers, computes numbered metrics (1–200),
    derives category breakdown and overall score, and creates summary.
    """
    cr = crawl_site(url)
    res = summarize_crawl(cr)
    m = res["metrics"]

    # Category scores (transparent, heuristic weights)
    # We’ll map the numbered metrics into seven buckets to drive visual cards.
    score_perf = _score_performance(m)
    score_mobile = _score_mobile(m)
    score_a11y = _score_accessibility(m)       # basic proxy from alt/structure
    score_security = _score_security(m, url)
    score_indexing = _score_indexing(m)
    score_metadata = _score_metadata(m)
    score_structure = _score_structure(m)

    # Weighted overall
    weights = {
        "Performance": 0.20,
        "Mobile": 0.15,
        "Accessibility": 0.10,
        "Security": 0.15,
        "Indexing": 0.15,
        "Metadata": 0.10,
        "Structure": 0.15,
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

    # Executive summary synthesis (rule-based ~200 words target)
    exec_summary = _generate_exec_summary(url, category_breakdown, strengths, weaknesses, fixes)

    # Build final metrics dict expected by templates
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
        # expose numbered metrics under table
        **m,
    }

    # Charts for PDF (status distribution etc.)
    charts = {
        "status_distribution": res["metrics"].get("173.Status Code Distribution") or {},
    }

    return {
        "metrics": out_metrics,
        "category_breakdown": category_breakdown,
        "charts": charts,
    }


# ------------------ Scoring helpers ------------------

def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))

def _score_performance(m: Dict[str, Any]) -> float:
    # Heuristic from total page size, requests per page, render blocking, excessive DOM
    size = float(m.get("84.Total Page Size") or 0)
    req = float(m.get("85.Requests Per Page") or 1)
    rbr = float(m.get("88.Render Blocking Resources") or 0)
    big_dom_pages = float(m.get("89.Excessive DOM Size") or 0)
    penalties = 0
    if size > 5_000_000: penalties += 15
    if req > 40: penalties += 20
    if rbr > 0: penalties += 10
    if big_dom_pages > 0: penalties += 10
    return _clamp(95 - penalties)

def _score_mobile(m: Dict[str, Any]) -> float:
    viewport_yes = float(m.get("98.Viewport Meta Tag") or 0)
    total_pages = float(m.get("15.Total Crawled Pages") or 1)
    ratio = viewport_yes / total_pages
    return _clamp(60 + 40 * ratio)

def _score_accessibility(m: Dict[str, Any]) -> float:
    missing_alt = float(m.get("55.Missing Image Alt Tags") or 0)
    total_images = max(missing_alt, 1)  # we did not store total images; conservative
    miss_ratio = missing_alt / total_images
    return _clamp(85 - (miss_ratio * 70))

def _score_security(m: Dict[str, Any], url: str) -> float:
    https_impl = float(m.get("105.HTTPS Implementation") or 0)
    mixed = float(m.get("108.Mixed Content") or 0)
    # if most pages https and low mixed content, high score
    total_pages = float(m.get("15.Total Crawled Pages") or 1)
    https_ratio = https_impl / total_pages
    penalties = 0
    if https_ratio < 0.7: penalties += 30
    if mixed > 0: penalties += 20
    return _clamp(95 - penalties)

def _score_indexing(m: Dict[str, Any]) -> float:
    non_canonical = float(m.get("31.Non-Canonical Pages") or 0)
    missing_can = float(m.get("32.Missing Canonical Tags") or 0)
    meta_blocked = float(m.get("30.Meta Robots Blocked URLs") or 0)
    total = float(m.get("15.Total Crawled Pages") or 1)
    penalties = (non_canonical + missing_can + meta_blocked) / max(total, 1) * 100
    return _clamp(95 - penalties)

def _score_metadata(m: Dict[str, Any]) -> float:
    missing_title = float(m.get("41.Missing Title Tags") or 0)
    missing_meta = float(m.get("45.Missing Meta Descriptions") or 0)
    total = float(m.get("15.Total Crawled Pages") or 1)
    miss_ratio = (missing_title + missing_meta) / max(total, 1)
    return _clamp(90 - (miss_ratio * 60))

def _score_structure(m: Dict[str, Any]) -> float:
    missing_h1 = float(m.get("49.Missing H1") or 0)
    multiple_h1 = float(m.get("50.Multiple H1") or 0)
    non_seo_urls = float(m.get("65.Non-SEO-Friendly URLs") or 0)
    total = float(m.get("15.Total Crawled Pages") or 1)
    penalties = (missing_h1 + multiple_h1 + non_seo_urls) / max(total, 1) * 100
    return _clamp(90 - penalties)


def _summarize_strengths_weaknesses(m: Dict[str, Any], cb: Dict[str, float]):
    strengths, weaknesses, fixes = [], [], []
    # Strengths
    for k, v in cb.items():
        if v >= 80:
            strengths.append(f"{k} is strong ({v:.0f}%).")
    # Weaknesses
    for k, v in cb.items():
        if v < 60:
            weaknesses.append(f"{k} below target ({v:.0f}%).")
    # Priority fixes (top 3 based on obvious issues)
    if (m.get("74.Broken External Links") or 0) > 0 or (m.get("27.Broken Internal Links") or 0) > 0:
        fixes.append("Resolve broken internal/external links to recover link equity and UX.")
    if (m.get("45.Missing Meta Descriptions") or 0) > 0 or (m.get("41.Missing Title Tags") or 0) > 0:
        fixes.append("Complete title & meta descriptions; enforce length and uniqueness.")
    if (m.get("32.Missing Canonical Tags") or 0) > 0 or (m.get("31.Non-Canonical Pages") or 0) > 0:
        fixes.append("Fix canonical implementation to consolidate signals.")
    if not fixes:
        fixes.append("Maintain current performance; monitor periodic changes and trends.")
    return strengths, weaknesses, fixes


def _generate_exec_summary(url: str, cb: Dict[str, float], strengths: list, weaknesses: list, fixes: list) -> str:
    parts = []
    parts.append(f"This report audits {url} across seven dimensions—Performance, Mobile, Accessibility, Security, Indexing, Metadata, and Structure—to produce an overall executive score.")
    parts.append(f"Category scores: " + ", ".join([f"{k} {v:.0f}%" for k, v in cb.items()]) + ".")
    if strengths:
        parts.append("Strengths: " + "; ".join(strengths) + ".")
    if weaknesses:
        parts.append("Weaknesses: " + "; ".join(weaknesses) + ".")
    parts.append("Priority actions: " + "; ".join(fixes) + ".")
    parts.append("Scores are derived from transparent heuristics (page size, requests, canonical/meta/alt coverage, HTTPS/mixed content) and can be extended with Core Web Vitals and backlink authority in future iterations.")
    return " ".join(parts)
