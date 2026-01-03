from typing import Dict
import requests
from bs4 import BeautifulSoup

# Minimal engine. Extend to 60–140+ metrics per your list.

def run_basic_audit(url: str) -> Dict:
    result = {
        "categories": {
            "Overall Site Health": {},
            "Crawlability & Indexation": {},
            "On-Page SEO": {},
            "Technical & Performance": {},
            "Mobile & Usability": {},
            "Security & HTTPS": {},
            "International SEO": {},
        },
        "raw": {}
    }
    try:
        resp = requests.get(url, timeout=15)
        status = resp.status_code
        result["categories"]["Crawlability & Indexation"]["http_status"] = {"value": status, "status": "good" if 200 <= status < 300 else "critical"}
        soup = BeautifulSoup(resp.text, "html.parser")
        # Title
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        result["categories"]["On-Page SEO"]["title_tag"] = {"value": title, "status": "good" if 10 <= len(title) <= 60 else "warning"}
        # Meta description
        md = soup.find("meta", attrs={"name": "description"})
        desc = md["content"].strip() if md and md.has_attr("content") else ""
        result["categories"]["On-Page SEO"]["meta_description"] = {"value": bool(desc), "status": "good" if 50 <= len(desc) <= 160 else ("warning" if desc else "critical")}
        # H1 presence
        h1 = soup.find("h1")
        result["categories"]["On-Page SEO"]["h1_presence"] = {"value": bool(h1), "status": "good" if h1 else "critical"}
        # Links sample broken ratio
        anchors = soup.find_all("a", href=True)
        broken = 0; total = 0
        for a in anchors[:150]:
            href = a["href"]
            if href.startswith("#") or href.startswith("mailto:"): continue
            total += 1
            try:
                target = href if href.startswith("http") else requests.compat.urljoin(url, href)
                r = requests.head(target, timeout=10, allow_redirects=True)
                if r.status_code >= 400:
                    broken += 1
            except:
                broken += 1
        broken_ratio = (broken / total) * 100 if total else 0
        result["categories"]["Crawlability & Indexation"]["broken_links_ratio"] = {"value": broken_ratio, "status": "good" if broken_ratio < 2 else ("warning" if broken_ratio < 10 else "critical")}
        # robots.txt
        try:
            rob = requests.get(requests.compat.urljoin(url, "/robots.txt"), timeout=5)
            result["categories"]["Crawlability & Indexation"]["robots_txt"] = {"value": rob.status_code == 200, "status": "good" if rob.status_code == 200 else "warning"}
        except:
            result["categories"]["Crawlability & Indexation"]["robots_txt"] = {"value": False, "status": "warning"}
        # HTTPS & security headers
        https = url.startswith("https://")
        result["categories"]["Security & HTTPS"]["https_enforced"] = {"value": https, "status": "good" if https else "critical"}
        headers = resp.headers
        csp = headers.get("Content-Security-Policy")
        hsts = headers.get("Strict-Transport-Security")
        xfo = headers.get("X-Frame-Options")
        result["categories"]["Security & HTTPS"]["security_headers"] = {
            "value": {"CSP": bool(csp), "HSTS": bool(hsts), "XFO": bool(xfo)},
            "status": "good" if all([csp, hsts, xfo]) else ("warning" if any([csp, hsts, xfo]) else "critical")
        }
        # Basic performance proxy
        page_size_kb = len(resp.content) / 1024
        result["categories"]["Technical & Performance"]["total_page_size_kb"] = {"value": round(page_size_kb, 1), "status": "good" if page_size_kb < 1500 else ("warning" if page_size_kb < 5000 else "critical")}
    except Exception as e:
        result["raw"]["error"] = str(e)
    return result


def strict_score(metrics: Dict) -> (int, str):
    status_points = {"good": 1.0, "warning": 0.5, "critical": 0.0}
    category_weights = {
        "Overall Site Health": 0.10,
        "Crawlability & Indexation": 0.20,
        "On-Page SEO": 0.20,
        "Technical & Performance": 0.20,
        "Mobile & Usability": 0.10,
        "Security & HTTPS": 0.15,
        "International SEO": 0.05,
    }
    total = 0.0
    for cat, items in metrics["categories"].items():
        if not items: continue
        cat_score = sum(status_points.get(v.get("status", "warning"), 0.5) for k, v in items.items())
        cat_score /= max(len(items), 1)
        total += cat_score * category_weights.get(cat, 0.0)
    score = int(round(total * 100))
    grade = "D"
    if score >= 95: grade = "A+"
    elif score >= 85: grade = "A"
    elif score >= 70: grade = "B"
    elif score >= 55: grade = "C"
    sec = metrics["categories"].get("Security & HTTPS", {})
    if any(v.get("status") == "critical" for v in sec.values()):
        if grade in ["A+", "A"]: grade = "B"
    return score, grade


def generate_summary_200(metrics: Dict, score: int, grade: str) -> str:
    strengths = []
    weaknesses = []
    for cat, items in metrics["categories"].items():
        good_items = [k for k, v in items.items() if v.get("status") == "good"]
        crit_items = [k for k, v in items.items() if v.get("status") == "critical"]
        if good_items: strengths.append(f"{cat}: " + ", ".join(good_items[:3]))
        if crit_items: weaknesses.append(f"{cat}: " + ", ".join(crit_items[:3]))
    s = " | ".join(strengths[:3]) or "Core setup present."
    w = " | ".join(weaknesses[:3]) or "No critical weaknesses detected."
    text = (
        f"This audit assigns a grade of {grade} with an overall score of {score}/100. "
        f"Strengths include: {s}. "
        f"However, key weaknesses were identified: {w}. "
        f"Prioritize enforcing HTTPS and comprehensive security headers, optimizing metadata (title and meta description), "
        f"resolving broken links, and reducing page weight to improve performance and Core Web Vitals. "
        f"Addressing these areas will enhance crawlability, user experience, and compliance readiness. "
        f"Schedule daily audits to track improvements and maintain high site health over time."
    )
    return text
