# fftech_audit/audit_engine.py (v2.1 — grounded scoring)
from __future__ import annotations
import datetime as dt
from typing import Dict, Any
from fftech_audit.crawlers import crawl_site
from fftech_audit.analyzers import summarize_crawl

def _grade_from_score(score: float) -> str:
    if score >= 95: return "A+"
    if score >= 85: return "A"
    if score >= 75: return "B"
    if score >= 65: return "C"
    if score >= 55: return "D"
    return "F"

def run_audit(url: str) -> Dict[str, Any]:
    cr = crawl_site(url)
    res = summarize_crawl(cr)
    m = res["metrics"]
    details = res.get("details", {})

    score_perf = _score_performance(m)
    score_mobile = _score_mobile(m)
    score_a11y = _score_accessibility(m, details)
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
    out_metrics["11.Site Health Score"] = round(overall, 1)

    charts = {
        # Use original dict (stored in details) for charts; metrics has JSON string for table
        "status_distribution": details.get("173.Status Code Distribution", {}),
    }
    return {"metrics": out_metrics, "category_breakdown": category_breakdown, "charts": charts}

# -------- scoring helpers
def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))

def _safe_total(m: Dict[str, Any]) -> float:
    return float(m.get("15.Total Crawled Pages", 1) or 1)

def _score_performance(m: Dict[str, Any]) -> float:
    total = _safe_total(m)
    ratio = (float(m.get("91.Large Pages", 0) or 0) + float(m.get("96.Resource Load Errors", 0) or 0)) / total
    return _clamp(100.0 - ratio * 80)

def _score_mobile(m: Dict[str, Any]) -> float:
    ratio = 1.0 - float(m.get("98.Viewport Meta Tag", 0) or 0) / _safe_total(m)
    return _clamp(ratio * 100)

def _score_accessibility(m: Dict[str, Any], details: Dict[str, Any]) -> float:
    total_imgs = int(details.get("total_images", 0) or 0)
    missing_alt = int(details.get("total_images_missing_alt", 0) or 0)
    ratio = missing_alt / max(total_imgs, 1)
    return _clamp(100.0 - ratio * 100)

def _score_security(m: Dict[str, Any]) -> float:
    https = float(m.get("105.HTTPS Implementation", 0) or 0)
    mixed = float(m.get("108.Mixed Content", 0) or 0)
    total = _safe_total(m)
    ratio = (total - https + mixed) / total
    return _clamp(100.0 - ratio * 100)

def _score_indexing(m: Dict[str, Any]) -> float:
    noindex = float(m.get("137.Noindex Issues", 0) or 0)
    sitemap = float(m.get("136.Sitemap Presence", 0) or 0)
    total = _safe_total(m)
    penalties = (noindex / total) * 30 + (1 - sitemap) * 20
    return _clamp(90.0 - penalties)

def _score_metadata(m: Dict[str, Any]) -> float:
    missing_title = float(m.get("41.Missing Title Tags") or 0)
    missing_meta = float(m.get("45.Missing Meta Descriptions") or 0)
    too_long = float(m.get("47.Meta Too Long") or 0)
    too_short = float(m.get("48.Meta Too Short") or 0)
    total = _safe_total(m)
    miss_ratio = (missing_title + missing_meta) / total
    length_issues = (too_long + too_short) / total
    penalties = miss_ratio * 60 + length_issues * 20
    return _clamp(90.0 - penalties)

def _score_structure(m: Dict[str, Any]) -> float:
    ratio = (float(m.get("49.Missing H1") or 0) +
             float(m.get("50.Multiple H1") or 0) +
             float(m.get("65.Non-SEO-Friendly URLs") or 0)) / _safe_total(m)
    return _clamp(90.0 - ratio * 100)

def _summarize_strengths_weaknesses(m: Dict[str, Any], cb: Dict[str, float]):
    strengths, weaknesses, fixes = [], [], []
    for k, v in cb.items():
        if v >= 80: strengths.append(f"{k} is strong ({v:.0f}%).")
    for k, v in cb.items():
        if v < 60: weaknesses.append(f"{k} below target ({v:.0f}%).")
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
    if strengths: parts.append("Strengths: " + "; ".join(strengths) + ".")
    if weaknesses: parts.append("Weaknesses: " + "; ".join(weaknesses) + ".")
    parts.append("Priority actions: " + "; ".join(fixes) + ".")
    parts.append("Scores are derived from transparent heuristics (avg page size, request counts incl. images, canonical/meta/alt coverage, HTTPS/mixed content) and can be extended with Core Web Vitals.")
    return " ".join(parts)
