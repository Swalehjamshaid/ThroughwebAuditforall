
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, List
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

@dataclass
class Metric:
    id: int
    name: str
    category: str
    value: Any
    score: float
    weight: float
    status: str
    description: str = ""

DEFAULT_TIMEOUT = 15
HEADERS = {"User-Agent": "FFTechAuditBot/1.0"}

def _safe_get(url: str) -> requests.Response:
    return requests.get(url, headers=HEADERS, timeout=DEFAULT_TIMEOUT, allow_redirects=True)


def audit_url(url: str) -> Dict[str, Any]:
    results: List[Metric] = []
    try:
        resp = _safe_get(url)
        status_code = resp.status_code
        content_len = len(resp.content or b"")
        parsed = urlparse(url)
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        return {
            "error": str(exc),
            "metrics": [],
            "category_scores": {k: 0 for k in list("ABCDEFGHI")},
            "overall": {"score": 0, "grade": "D"},
        }

    health_score = 100 if 200 <= status_code < 300 else 60 if 300 <= status_code < 400 else 20
    results.append(Metric(11, "Site Health Score", "B", health_score, health_score, 1.0, "computed"))
    results.append(Metric(12, "Total Errors", "B", 0 if 200 <= status_code < 400 else 1, 100 if 200 <= status_code < 400 else 20, 0.6, "computed"))
    results.append(Metric(13, "Total Warnings", "B", 0, 100, 0.2, "computed"))
    results.append(Metric(14, "Total Notices", "B", 0, 100, 0.2, "computed"))

    kb = round(content_len / 1024, 2)
    size_score = 100 if kb < 1024 else 70 if kb < 2048 else 40
    results.append(Metric(84, "Total Page Size (KB)", "E", kb, size_score, 1.0, "computed"))

    title = (soup.title.string.strip() if soup.title and soup.title.string else "")
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_desc = meta_desc_tag.get("content", "").strip() if meta_desc_tag else ""

    results.append(Metric(41, "Missing Title Tags", "D", 0 if title else 1, 100 if title else 0, 1.0, "computed"))
    results.append(Metric(43, "Title Too Long", "D", len(title) > 60, 100 if len(title) <= 60 else 60, 0.4, "computed"))
    results.append(Metric(45, "Missing Meta Descriptions", "D", 0 if meta_desc else 1, 100 if meta_desc else 0, 1.0, "computed"))
    results.append(Metric(47, "Meta Too Long", "D", len(meta_desc) > 160, 100 if len(meta_desc) <= 160 else 60, 0.4, "computed"))

    h1s = soup.find_all("h1")
    results.append(Metric(49, "Missing H1", "D", 0 if h1s else 1, 100 if h1s else 0, 1.0, "computed"))
    results.append(Metric(50, "Multiple H1", "D", len(h1s) > 1, 80 if len(h1s) == 1 else 60 if len(h1s) > 1 else 0, 0.5, "computed"))

    imgs = soup.find_all("img")
    missing_alt = sum(1 for i in imgs if not i.get("alt"))
    alt_score = 100 if missing_alt == 0 else max(20, 100 - (missing_alt * 10))
    results.append(Metric(55, "Missing Image Alt Tags", "D", missing_alt, alt_score, 0.8, "computed"))

    ld_json = soup.find_all("script", attrs={"type": "application/ld+json"})
    results.append(Metric(59, "Missing Structured Data", "D", 0 if ld_json else 1, 100 if ld_json else 40, 1.0, "computed"))

    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    og_ok = bool(og_title and og_desc)
    results.append(Metric(62, "Missing Open Graph Tags", "D", 0 if og_ok else 1, 100 if og_ok else 40, 0.6, "computed"))

    a_tags = soup.find_all("a", href=True)
    internal, external = 0, 0
    for a in a_tags:
        href = a["href"]
        if href.startswith("#"):
            continue
        if href.startswith("/") or urlparse(url).netloc in href:
            internal += 1
        else:
            external += 1
    results.append(Metric(73, "External Links Count", "D", external, 100 if external <= 100 else 60, 0.3, "computed"))

    robots_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}/robots.txt"
    sitemap_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}/sitemap.xml"
    try:
        r = _safe_get(robots_url)
        robots_present = (r.status_code == 200)
    except Exception:
        robots_present = False
    try:
        s = _safe_get(sitemap_url)
        sitemap_present = (s.status_code == 200)
    except Exception:
        sitemap_present = False
    results.append(Metric(136, "Sitemap Presence", "F", sitemap_present, 100 if sitemap_present else 40, 1.0, "computed"))

    unsupported_perf_ids = [76,77,78,79,80,81,82,83,91,96]
    for mid in unsupported_perf_ids:
        results.append(Metric(mid, f"Perf Metric {mid}", "E", None, 0, 0.0, "unsupported", "Requires lab/RUM tooling"))

    category_scores = {k: 0.0 for k in list("ABCDEFGHI")}
    weights_total = {k: 0.0 for k in list("ABCDEFGHI")}
    for m in results:
        category_scores[m.category] += (m.score * m.weight)
        weights_total[m.category] += m.weight
    for k in category_scores:
        category_scores[k] = round(category_scores[k] / weights_total[k], 2) if weights_total[k] > 0 else 0.0

    overall_health = category_scores["B"]
    strengths = ["Has title" if title else ""] + (["Has meta description"] if meta_desc else [])
    weaknesses = []
    if missing_alt:
        weaknesses.append(f"{missing_alt} images missing alt")
    if not ld_json:
        weaknesses.append("No structured data")
    if not sitemap_present:
        weaknesses.append("No sitemap.xml")

    exec_summary = {
        "Overall Site Health Score (%)": overall_health,
        "Strengths": [s for s in strengths if s],
        "Weaknesses": weaknesses,
        "Priority Fixes": [
            "Add/optimize meta description" if not meta_desc else "Review meta length",
            "Add structured data (JSON-LD)",
            "Ensure single H1 per page" if len(h1s) != 1 else "H1 OK",
        ],
    }

    metrics_data = [m.__dict__ for m in results]
    return {
        "url": url,
        "metrics": metrics_data,
        "category_scores": category_scores,
        "executive_summary": exec_summary,
    }
