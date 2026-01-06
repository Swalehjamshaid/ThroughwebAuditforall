
# engine.py — updated with one-page competitor analysis
from typing import Dict, Any, List, Tuple
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse
from html.parser import HTMLParser
import re
import ssl

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) FFTechAudit/1.0 "
    "Chrome/119.0 Safari/537.36"
)
ACCEPT_LANG = "en-US,en;q=0.9"
TIMEOUT_S = 10  # keep modest to avoid hanging audits

# ----------------------------
# HTML tag collector (lightweight)
# ----------------------------
class TagCollector(HTMLParser):
    """
    Collect start tags and attributes in a normalized, lower-case manner.
    This allows fast presence checks for <meta name="viewport">, canonical etc.
    """
    def __init__(self):
        super().__init__()
        self.tags: List[Tuple[str, Dict[str, str]]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag.lower(), {k.lower(): (v or "") for k, v in attrs}))


# ----------------------------
# Network helpers
# ----------------------------

def _fetch(url: str) -> Tuple[int, bytes, Dict[str, str]]:
    """
    Fetch URL with realistic headers and a safe TLS context.
    Returns: (status_code, body_bytes, headers_dict_lowercased)
    """
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": ACCEPT_LANG,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Connection": "close",
        },
    )
    ctx = ssl.create_default_context()  # standard verification (no CA tweaking)
    try:
        with urlopen(req, timeout=TIMEOUT_S, context=ctx) as resp:
            status = resp.getcode()
            headers = {k.lower(): v for k, v in resp.info().items()}
            data = resp.read() or b""
            return status, data, headers
    except HTTPError as e:
        return e.code, b"", {k.lower(): v for k, v in (e.headers or {}).items()}
    except URLError as e:
        return 0, b"", {"error": str(e)}
    except Exception as e:
        return 0, b"", {"error": str(e)}


def _get_text(data: bytes) -> str:
    """Decode response bytes defensively to text."""
    try:
        text = data.decode("utf-8", errors="ignore")
        if not text:
            text = data.decode("latin-1", errors="ignore")
        return text
    except Exception:
        return ""


# ----------------------------
# Robots & sitemap
# ----------------------------

def _robots_allowed(base: str) -> bool:
    """
    Check robots.txt for a full block: 'User-agent: *' + 'Disallow: /'.
    If robots.txt can't be fetched, default to allowed.
    """
    p = urlparse(base)
    robots = f"{p.scheme}://{p.netloc}/robots.txt"
    status, body, _ = _fetch(robots)
    if status == 0:
        return True
    text = _get_text(body).lower()
    if "user-agent: *" in text and "disallow: /" in text:
        return False
    return True


def _sitemap_present(base: str) -> bool:
    """Quick existence probe for common sitemap endpoints."""
    p = urlparse(base)
    for name in ("sitemap.xml", "sitemap_index.xml"):
        url = f"{p.scheme}://{p.netloc}/{name}"
        status, _, _ = _fetch(url)
        if status and 200 <= status < 400:
            return True
    return False


# ----------------------------
# Scoring helpers
# ----------------------------

def _score_bounds(val: int) -> int:
    return max(0, min(100, val))


def _total_score(cats: Dict[str, int]) -> int:
    """Simple aggregate across categories for coarse ranking."""
    return sum(int(v or 0) for v in cats.values())


def _normalize_url(url: str) -> str:
    """Ensure the URL has a scheme; default to https."""
    if not url:
        return url
    p = urlparse(url)
    if not p.scheme:
        return "https://" + url.lstrip("/")
    return url


# ----------------------------
# Main audit function
# ----------------------------

def run_basic_checks(url: str) -> Dict[str, Any]:
    """
    Dependency-free heuristics for Performance, Accessibility, SEO, Security, BestPractices.

    Returns:
        {
            "category_scores": { ... },
            "metrics": { ... },        # raw technical metrics (keys align with main.py presenter)
            "top_issues": [ ... ]      # concise text items shown in the UI list
        }
    """
    url = _normalize_url(url)

    metrics: Dict[str, Any] = {}
    issues: List[str] = []
    cats: Dict[str, int] = {
        "Performance": 60,
        "Accessibility": 60,
        "SEO": 60,
        "Security": 60,
        "BestPractices": 60,
    }

    # Fetch
    status, body, headers = _fetch(url)
    metrics["status_code"] = status
    metrics["content_length"] = len(body)
    metrics["content_encoding"] = headers.get("content-encoding", "")
    metrics["cache_control"] = headers.get("cache-control", "")
    metrics["hsts"] = headers.get("strict-transport-security", "")
    metrics["xcto"] = headers.get("x-content-type-options", "")
    metrics["xfo"] = headers.get("x-frame-options", "")
    metrics["csp"] = headers.get("content-security-policy", "")
    metrics["set_cookie"] = headers.get("set-cookie", "")

    text = _get_text(body)

    # Parse HTML
    collector = TagCollector()
    try:
        collector.feed(text)
    except Exception:
        # Continue even if parsing fails, we still have header-level metrics
        pass

    # Helper: return attrs for a given tag name
    def tags(name: str):
        return [a for t, a in collector.tags if t == name]

    # Title extraction (regex fallback to be resilient)
    titles = tags("title")
    title_text = ""
    if titles or text:
        m = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
        title_text = (m.group(1).strip() if m else "")
    metrics["title"] = title_text
    metrics["title_length"] = len(title_text)

    # Meta fields
    metas = tags("meta")
    meta_desc = ""
    meta_robots = ""
    for a in metas:
        n = a.get("name", "")
        prop = a.get("property", "")
        if n == "description" or prop == "og:description":
            meta_desc = a.get("content", "") or meta_desc
        if n == "robots":
            meta_robots = a.get("content", "") or meta_robots
    metrics["meta_description_length"] = len(meta_desc)
    metrics["meta_robots"] = meta_robots

    # Canonical detection (support multi-rel values)
    canonicals = []
    for a in tags("link"):
        rel = (a.get("rel", "") or "").lower()
        if "canonical" in rel.split() or "canonical" in rel:
            href = a.get("href", "")
            if href:
                canonicals.append(href)
    metrics["canonical_present"] = bool(canonicals)

    # Headings and images
    h1s = tags("h1")
    metrics["h1_count"] = len(h1s)

    imgs = tags("img")
    img_count = len(imgs)
    img_missing_alt = sum(1 for a in imgs if not a.get("alt"))
    metrics["image_count"] = img_count
    metrics["images_without_alt"] = img_missing_alt

    # Accessibility helpers
    has_lang = any("lang" in a for t, a in collector.tags if t == "html")
    has_viewport = any(a.get("name", "") == "viewport" for a in metas)
    metrics["html_lang_present"] = has_lang
    metrics["viewport_present"] = has_viewport

    # Robots & sitemap
    robots_ok = _robots_allowed(url)
    metrics["robots_allowed"] = robots_ok
    sitemap_ok = _sitemap_present(url)
    metrics["sitemap_present"] = sitemap_ok

    # Security heuristics
    parsed = urlparse(url)
    https = parsed.scheme.lower() == "https"
    metrics["has_https"] = https

    # ------------------------
    # Scoring (balanced)
    # ------------------------
    # Performance: payload, compression, caching
    perf = 100
    size = metrics["content_length"]
    if size == 0:
        perf -= 30
        issues.append("No content received; check availability and payload.")
    elif size > 250_000:  # friendlier threshold for rich homepages
        perf -= min(40, (size - 250_000) // 30_000)
    if metrics["content_encoding"] not in ("gzip", "br", "deflate"):
        perf -= 8
        issues.append("Response not compressed (gzip/br/deflate).")
    if not metrics["cache_control"]:
        perf -= 8
        issues.append("Missing Cache-Control headers.")
    cats["Performance"] = _score_bounds(perf)

    # Accessibility: alt text, viewport, lang, heading presence
    acc = 100
    if img_missing_alt > 0:
        acc -= min(28, img_missing_alt * 2)
        issues.append(f"{img_missing_alt} <img> tags without alt attribute.")
    if not has_viewport:
        acc -= 10
        issues.append("No mobile viewport meta.")
    if not has_lang:
        acc -= 10
        issues.append("<html lang> missing for language semantics.")
    if metrics["h1_count"] == 0:
        acc -= 10
        issues.append("Missing <h1> heading.")
    cats["Accessibility"] = _score_bounds(acc)

    # SEO: title, description, canonical, robots/sitemap
    seo = 100
    tl = metrics["title_length"]
    if tl == 0:
        seo -= 18
        issues.append("Missing <title> tag.")
    elif tl < 12 or tl > 70:
        seo -= 8
        issues.append("Title length suboptimal (12–70 chars).")
    mdl = metrics["meta_description_length"]
    if mdl == 0:
        seo -= 12
        issues.append("Missing meta description.")
    elif mdl < 40 or mdl > 170:
        seo -= 4
        issues.append("Meta description length suboptimal (40–170 chars).")
    if not metrics["canonical_present"]:
        seo -= 8
        issues.append("Missing canonical link.")
    if "noindex" in (metrics["meta_robots"] or "").lower():
        seo -= 18
        issues.append("Meta robots set to noindex.")
    if not robots_ok:
        seo -= 15
        issues.append("robots.txt disallows all (User-agent: * / Disallow: /).")
    if not sitemap_ok:
        seo -= 5
        issues.append("No sitemap.xml discovered.")
    cats["SEO"] = _score_bounds(seo)

    # Security: HTTPS, HSTS, headers
    sec = 100
    if not https:
        sec -= 22
        issues.append("Site not served over HTTPS.")
    if not metrics["hsts"]:
        sec -= 8
        issues.append("Missing Strict-Transport-Security (HSTS).")
    if (metrics["xcto"] or "").lower() != "nosniff":
        sec -= 8
        issues.append("Missing X-Content-Type-Options: nosniff.")
    if not metrics["xfo"]:
        sec -= 5
        issues.append("Missing X-Frame-Options (clickjacking risk).")
    if not metrics["csp"]:
        sec -= 8
        issues.append("Missing Content-Security-Policy.")
    sc = metrics["set_cookie"] or ""
    if sc and ("httponly" not in sc.lower() or "secure" not in sc.lower()):
        sec -= 5
        issues.append("Cookies missing Secure/HttpOnly flags.")
    cats["Security"] = _score_bounds(sec)

    # Best Practices: OpenGraph, favicon, landmarks
    bp = 100
    og_title = any(a.get("property", "") == "og:title" for a in metas)
    og_image = any(a.get("property", "") == "og:image" for a in metas)
    if not og_title or not og_image:
        bp -= 5
        issues.append("Missing OpenGraph tags (og:title/og:image).")
    has_favicon = any("icon" in (a.get("rel", "") or "").lower() for a in tags("link"))
    if not has_favicon:
        bp -= 3
        issues.append("No favicon link found.")
    has_main = any(t == "main" for t, _ in collector.tags)
    has_nav = any(t == "nav" for t, _ in collector.tags)
    if not has_main:
        bp -= 3
        issues.append("No <main> landmark found.")
    if not has_nav:
        bp -= 2
        issues.append("No <nav> landmark found.")
    cats["BestPractices"] = _score_bounds(bp)

    # If status indicates failure, soften scores but keep baseline
    if status == 0 or status >= 400:
        issues.append(f"HTTP status {status} detected; using heuristic baseline.")
        cats["Performance"] = max(30, cats["Performance"] - 18)
        cats["SEO"] = max(30, cats["SEO"] - 12)

    return {
        "category_scores": cats,
        "metrics": metrics,
        "top_issues": issues,
    }


# ----------------------------
# One-page competitor analysis
# ----------------------------

def run_competitor_analysis_one_page(target_url: str, competitor_urls: List[str]) -> Dict[str, Any]:
    """
    Compare the target URL against a list of competitor URLs using a single-page audit
    (homepage or provided page only). Returns a structured comparative report.

    Args:
        target_url: The site/page to benchmark.
        competitor_urls: List of competitor sites/pages to compare.

    Returns:
        {
            "target": { "url": str, "scores": {...}, "metrics": {...}, "issues": [...] , "total": int },
            "competitors": [ { "url": str, "scores": {...}, "metrics": {...}, "issues": [...], "total": int }, ... ],
            "comparison_table": [ { "url": str, "Performance": int, "Accessibility": int, "SEO": int, "Security": int, "BestPractices": int, "Total": int }, ... ],
            "winners_by_category": { category: url },
            "deltas_vs_target": { competitor_url: { category: int (competitor - target) } },
            "key_findings": { "target_strengths": [str], "target_gaps": [str] }
        }
    """
    target_url = _normalize_url(target_url)
    competitor_urls = [_normalize_url(u) for u in competitor_urls if u]

    # Audit target
    target_res = run_basic_checks(target_url)
    target_entry = {
        "url": target_url,
        "scores": target_res["category_scores"],
        "metrics": target_res["metrics"],
        "issues": target_res["top_issues"],
        "total": _total_score(target_res["category_scores"]),
    }

    # Audit competitors
    competitors: List[Dict[str, Any]] = []
    for cu in competitor_urls:
        res = run_basic_checks(cu)
        competitors.append({
            "url": cu,
            "scores": res["category_scores"],
            "metrics": res["metrics"],
            "issues": res["top_issues"],
            "total": _total_score(res["category_scores"]),
        })

    # Build comparison table
    comparison_table: List[Dict[str, Any]] = []
    for entry in [target_entry] + competitors:
        row = {
            "url": entry["url"],
            "Performance": entry["scores"].get("Performance", 0),
            "Accessibility": entry["scores"].get("Accessibility", 0),
            "SEO": entry["scores"].get("SEO", 0),
            "Security": entry["scores"].get("Security", 0),
            "BestPractices": entry["scores"].get("BestPractices", 0),
            "Total": entry["total"],
        }
        comparison_table.append(row)

    # Determine winners by category
    categories = ["Performance", "Accessibility", "SEO", "Security", "BestPractices"]
    winners_by_category: Dict[str, str] = {}
    for cat in categories:
        best_url = None
        best_score = -1
        for entry in [target_entry] + competitors:
            score = entry["scores"].get(cat, 0)
            if score > best_score:
                best_score = score
                best_url = entry["url"]
        winners_by_category[cat] = best_url or ""

    # Deltas vs target for each competitor
    deltas_vs_target: Dict[str, Dict[str, int]] = {}
    for comp in competitors:
        comp_url = comp["url"]
        deltas: Dict[str, int] = {}
        for cat in categories:
            deltas[cat] = comp["scores"].get(cat, 0) - target_entry["scores"].get(cat, 0)
        deltas_vs_target[comp_url] = deltas

    # Key findings: strengths and gaps for the target
    strengths: List[str] = []
    gaps: List[str] = []
    for cat in categories:
        winner = winners_by_category.get(cat)
        target_score = target_entry["scores"].get(cat, 0)
        # Strength: target is winner (or tied for max)
        max_score = max(row[cat] for row in comparison_table)
        if target_score == max_score:
            strengths.append(f"Strong {cat} ({target_score}) relative to peer set.")
        else:
            # Gap: nearest competitor ahead by at least 5 points
            ahead_by = max(0, max(row[cat] for row in comparison_table[1:]) - target_score)
            if ahead_by >= 5:
                gaps.append(f"Improve {cat}: competitors lead by ~{ahead_by} points.")

    return {
        "target": target_entry,
        "competitors": competitors,
        "comparison_table": comparison_table,
        "winners_by_category": winners_by_category,
        "deltas_vs_target": deltas_vs_target,
        "key_findings": {
            "target_strengths": strengths,
            "target_gaps": gaps,
        },
    }


if __name__ == "__main__":
    # Example quick run (manually):
    # python engine.py
    target = "example.com"  # will be normalized to https://example.com
    rivals = ["iana.org", "ietf.org"]
    report = run_competitor_analysis_one_page(target, rivals)
    # Minimal printout for sanity check
    from pprint import pprint
    pprint(report["comparison_table"])
