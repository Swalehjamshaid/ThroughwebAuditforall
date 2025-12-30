
# fftech_audit/audit_engine.py
import datetime as dt
from typing import Dict, Any
from urllib.parse import urlparse

def _grade_from_score(score: float) -> str:
    # Simple mapping (adjust later with your model / signals)
    if score >= 90: return "A+"
    if score >= 80: return "A"
    if score >= 70: return "B"
    if score >= 60: return "C"
    if score >= 50: return "D"
    return "F"

def _percent(v: float, min_v=0.0, max_v=100.0) -> float:
    return max(min(v, max_v), min_v)

def run_audit(url: str) -> Dict[str, Any]:
    """
    Deterministic stub that returns a realistic metrics shape compatible
    with results.html. Replace these signals with real checks (HTTP, HTML, SEO).
    """
    parsed = urlparse(url)
    host_ok = bool(parsed.scheme in ("http", "https") and parsed.netloc)

    # Example signals (expand to 200+):
    meta_title_len = 62.0
    meta_desc_len = 150.0
    h1_count = 1.0
    indexing_ok = 1.0
    robots_ok = 1.0
    sitemap_ok = 1.0
    speed_score = 78.5
    mobile_ok = 84.0
    a11y_score = 71.0
    security_https = 100.0 if parsed.scheme == "https" else 50.0
    canonical_ok = 80.0

    # Weighted overall
    weights = {
        "speed": 0.20,
        "mobile": 0.15,
        "a11y": 0.10,
        "security": 0.15,
        "indexing": 0.15,
        "meta": 0.10,
        "structure": 0.15,
    }
    meta_score = _percent( (meta_title_len/70)*50 + (meta_desc_len/160)*50 )  # simple
    structure_score = _percent( (h1_count >= 1) * 80 + (canonical_ok/100)*20 )
    indexing_score = _percent( (indexing_ok*50)+(robots_ok*25)+(sitemap_ok*25) )

    overall = (
        speed_score*weights["speed"] +
        mobile_ok*weights["mobile"] +
        a11y_score*weights["a11y"] +
        security_https*weights["security"] +
        indexing_score*weights["indexing"] +
        meta_score*weights["meta"] +
        structure_score*weights["structure"]
    )

    # Summary buckets for chips
    category_breakdown = {
        "Performance": round(speed_score, 1),
        "Mobile": round(mobile_ok, 1),
        "Accessibility": round(a11y_score, 1),
        "Security": round(security_https, 1),
        "Indexing": round(indexing_score, 1),
        "Metadata": round(meta_score, 1),
        "Structure": round(structure_score, 1),
    }

    strengths = []
    weaknesses = []
    priority_fixes = []

    if speed_score >= 75: strengths.append("Good page speed performance.")
    else:
        weaknesses.append("Page speed below target.")
        priority_fixes.append("Optimize images, enable compression, reduce render-blocking resources.")

    if security_https >= 90: strengths.append("Site uses HTTPS correctly.")
    else:
        weaknesses.append("HTTPS not fully enforced.")
        priority_fixes.append("Enforce HTTPS and fix mixed content.")

    if mobile_ok >= 80: strengths.append("Mobile friendliness is strong.")
    else:
        weaknesses.append("Mobile layout issues detected.")
        priority_fixes.append("Improve responsive layout and tap targets.")

    if a11y_score >= 70: strengths.append("Accessibility above baseline.")
    else:
        weaknesses.append("Accessibility needs improvements.")
        priority_fixes.append("Add alt text, improve contrast, and ARIA labels.")

    metrics: Dict[str, Any] = {
        "target.url": url,
        "generated_at": dt.datetime.utcnow().isoformat(),
        "overall.health_score": round(_percent(overall), 1),
        "overall.grade": _grade_from_score(overall),
        # Example raw signals:
        "signals.meta.title_length": meta_title_len,
        "signals.meta.description_length": meta_desc_len,
        "signals.structure.h1_count": h1_count,
        "signals.indexing.ok": bool(indexing_ok),
        "signals.robots.ok": bool(robots_ok),
        "signals.sitemap.ok": bool(sitemap_ok),
        "signals.performance.score": speed_score,
        "signals.mobile.score": mobile_ok,
        "signals.a11y.score": a11y_score,
        "signals.security.https_score": security_https,
        "signals.canonical.ok_score": canonical_ok,
        # Executive summary:
        "summary.strengths": strengths,
        "summary.weaknesses": weaknesses,
        "summary.priority_fixes": priority_fixes,
        "summary.category_breakdown": category_breakdown,
    }
    return metrics
