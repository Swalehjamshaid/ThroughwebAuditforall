
# fftech_audit/audit_engine.py (v2.2 — grounded scoring + competitor analysis + rows)
from __future__ import annotations
import os
import datetime as dt
from typing import Dict, Any, List, Tuple
from fftech_audit.crawlers import crawl_site
from fftech_audit.analyzers import summarize_crawl

# ----- brand competitors (override via env COMPETITOR_URLS, comma-separated)
_PK_APPLIANCE_COMPETITORS = [
    "https://www.dawlance.com.pk",
    "https://orient.com.pk",
    "https://pel.com.pk",
    "https://kenwoodpakistan.com",
    "https://www.samsung.com/pk/",
]

def _grade_from_score(score: float) -> str:
    if score >= 95: return "A+"
    if score >= 85: return "A"
    if score >= 75: return "B"
    if score >= 65: return "C"
    if score >= 55: return "D"
    return "F"

def run_audit(url: str) -> Dict[str, Any]:
    target = (url or "").strip() or "https://www.haier.com.pk"
    cr = crawl_site(target, max_pages=int(os.getenv("MAX_PAGES_MAIN", "120")))
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
    exec_summary = _generate_exec_summary(target, category_breakdown, strengths, weaknesses, fixes)

    # fill signal rows for results.html
    rows = [{"label": k, "value": v} for k, v in category_breakdown.items()]

    out_metrics: Dict[str, Any] = {
        "target.url": target,
        "generated_at": dt.datetime.utcnow().isoformat(),
        "overall.health_score": round(overall, 1),
        "overall.grade": _grade_from_score(overall),
        "summary.strengths": strengths,
        "summary.weaknesses": weaknesses,
        "summary.priority_fixes": fixes,
        "summary.category_breakdown": category_breakdown,
        "summary.executive": exec_summary,
        "rows": rows,   # ensure non-empty signals
        **m,
    }
    out_metrics["11.Site Health Score"] = round(overall, 1)

    # ----- competitor analysis (lightweight)
    competitors_cfg = os.getenv("COMPETITOR_URLS", "")
    competitors_list = [u.strip() for u in competitors_cfg.split(",") if u.strip()] or _PK_APPLIANCE_COMPETITORS
    max_pages_comp = int(os.getenv("MAX_PAGES_COMP", "40"))

    comp_results: List[Dict[str, Any]] = []
    for cu in competitors_list:
        try:
            ccr = crawl_site(cu, max_pages=max_pages_comp)
            cres = summarize_crawl(ccr)
            cm = cres["metrics"]
            cd = cres.get("details", {})
            cps = _score_performance(cm)
            cmo = _score_mobile(cm)
            ca11y = _score_accessibility(cm, cd)
            csec = _score_security(cm)
            cind = _score_indexing(cm)
            cmeta = _score_metadata(cm)
            cstr = _score_structure(cm)
            cov = (
                cps * weights["Performance"] +
                cmo * weights["Mobile"] +
                ca11y * weights["Accessibility"] +
                csec * weights["Security"] +
                cind * weights["Indexing"] +
                cmeta * weights["Metadata"] +
                cstr * weights["Structure"]
            )
            comp_results.append({
                "url": cu,
                "overall": round(cov, 1),
                "grade": _grade_from_score(cov),
                "breakdown": {
                    "Performance": round(cps, 1),
                    "Mobile": round(cmo, 1),
                    "Accessibility": round(ca11y, 1),
                    "Security": round(csec, 1),
                    "Indexing": round(cind, 1),
                    "Metadata": round(cmeta, 1),
                    "Structure": round(cstr, 1),
                }
            })
        except Exception:
            comp_results.append({"url": cu, "overall": 0.0, "grade": "F", "breakdown": {}})

    charts = {
        "status_distribution": details.get("173.Status Code Distribution", {}),
        "competitor_scores": [{"url": r["url"], "score": r["overall"]} for r in comp_results],
    }

    return {
        "metrics": out_metrics,
        "category_breakdown": category_breakdown,
        "charts": charts,
        "competitors": comp_results,
    }

# -------- scoring helpers
def _clamp(x: float) -> float: return max(0.0, min(100.0, x))
def _safe_total(m: Dict[str, Any]) -> float:
    t = float(m.get("15.Total Crawled Pages") or 0)
    return t if t > 0 else 1

def _score_performance(m: Dict[str, Any]) -> float:
    size_bytes = float(m.get("84.Total Page Size") or 0)  # avg per page
    req = float(m.get("85.Requests Per Page") or 1)
    rbr_pages = float(m.get("88.Render Blocking Resources") or 0)
    big_dom_pages = float(m.get("89.Excessive DOM Size") or 0)
    total = _safe_total(m)
    rbr_ratio = rbr_pages / total
    big_dom_ratio = big_dom_pages / total
    penalties = 0.0
    # Size penalties
    if size_bytes > 2_000_000: penalties += 22
    elif size_bytes > 1_000_000: penalties += 12
    # Request count penalties (includes images now)
    if req > 80: penalties += 24
    elif req > 50: penalties += 12
    # Render-blocking and DOM penalties
    penalties += rbr_ratio * 22
    penalties += big_dom_ratio * 18
    base = 96.0
    return _clamp(base - penalties)

def _score_mobile(m: Dict[str, Any]) -> float:
    ratio = float(m.get("98.Viewport Meta Tag") or 0) / _safe_total(m)
    return _clamp(55.0 + 45.0 * ratio)

def _score_accessibility(m: Dict[str, Any], details: Dict[str, Any]) -> float:
    missing_alt = float(m.get("55.Missing Image Alt Tags") or 0)
    total_images = float(details.get("total_images") or 0)
    if total_images <= 0:
        miss_ratio = 0.0 if missing_alt == 0 else 0.5
    else:
        miss_ratio = missing_alt / total_images
    return _clamp(92.0 - miss_ratio * 60)

def _score_security(m: Dict[str, Any]) -> float:
    https_impl = float(m.get("105.HTTPS Implementation") or 0)
    mixed = float(m.get("108.Mixed Content") or 0)
    https_ratio = https_impl / _safe_total(m)
    penalties = 0.0
    if https_ratio < 0.9: penalties += 20
    if https_ratio < 0.7: penalties += 35
    if mixed > 0: penalties += min(30.0, mixed * 3.0)
    return _clamp(95.0 - penalties)

def _score_indexing(m: Dict[str, Any]) -> float:
    ratio = (float(m.get("31.Non-Canonical Pages") or 0) +
             float(m.get("32.Missing Canonical Tags") or 0) +
             float(m.get("30.Meta Robots Blocked URLs") or 0)) / _safe_total(m)
    return _clamp(95.0 - ratio * 100)

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
    if (m.get("108.Mixed Content", 0) or 0) > 0:
        fixes.append("Eliminate mixed HTTP assets on HTTPS pages (use HTTPS-only resources).")
    if (m.get("94.Browser Caching Issues", 0) or 0) > 0:
        fixes.append("Set Cache-Control with sufficient max-age to improve repeat performance.")
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
    parts.append("Scores are derived from transparent heuristics (avg page size, request counts incl. images, canonical/meta/alt coverage, HTTPS/mixed content, viewport meta) and optionally Core Web Vitals via Lighthouse.")
    return " ".join(parts)
