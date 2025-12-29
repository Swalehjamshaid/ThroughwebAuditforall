
# fftech_audit/audit_engine.py
"""
AuditEngine (homepage quick audit) + 200-metric registry
- Robust HTML parsing (real tags; no &lt;/&gt;)
- Transparent scoring: Score, Grade, Category breakdowns
"""

import re, time, json, datetime, requests
from typing import Dict, Any, List, Tuple
from urllib.parse import urlparse, urljoin

APP_BRAND = "FF Tech"

def now_utc() -> datetime.datetime:
    return datetime.datetime.utcnow()

def is_valid_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except:
        return False

def safe_request(url: str, timeout: int = 10) -> Tuple[int, bytes, float, Dict[str, str]]:
    t0 = time.time()
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "FFTechAuditBot/1.0"})
        latency = time.time() - t0
        return resp.status_code, resp.content or b"", latency, dict(resp.headers or {})
    except Exception:
        return 0, b"", time.time() - t0, {}

def grade_from_score(score: int) -> str:
    return ("A+" if score>=95 else "A" if score>=90 else "A-" if score>=85 else
            "B+" if score>=80 else "B" if score>=75 else "B-" if score>=70 else
            "C+" if score>=65 else "C" if score>=60 else "C-" if score>=55 else
            "D+" if score>=50 else "D")

# Metric descriptors 1..200
METRIC_DESCRIPTORS: Dict[int, Dict[str, Any]] = {}
def register_metrics():
    sections = {
        "A": ["Overall Site Health (%)","Website Grade","Executive Summary","Strengths","Weak areas","Priority fixes",
              "Severity (errors, warnings, notices)","Category scores","Industry-standard presentation","Export readiness"],
        "C": ["HTTP 2xx","HTTP 4xx","HTTP 5xx","Broken internal links","Broken external links","robots.txt","Sitemap presence",
              "Canonical present","Open Graph/Twitter presence"],
        "D": ["Missing title","Title too long","Title too short","Missing meta description","Meta too long","Meta too short",
              "Missing H1","Multiple H1","Missing image alts","URL length","Uppercase in URL"],
        "E": ["Total page size KB","Requests per page (approx)","Server response ms","Caching missing","Compression enabled",
              "Render-blocking approx","Approx DOM nodes","3rd-party scripts","Potentially large images","Lazy loading missing"],
        "F": ["Viewport meta present","HTTPS enabled","Mixed content","Missing security headers"],
        "X": ["Crawlability score","On-page SEO score","Performance score","Security score","Mobile score",
              "Fix priority","Risk severity","Quick wins","Speed improvement potential","Security improvement potential","Growth readiness"]
    }
    idx = 1
    for cat, names in sections.items():
        for name in names:
            METRIC_DESCRIPTORS[idx] = {"name": name, "category": cat}
            idx += 1
    # fill to 200
    while idx <= 200:
        METRIC_DESCRIPTORS[idx] = {"name": f"Placeholder {idx}", "category": "Z"}
        idx += 1
register_metrics()

class AuditEngine:
    def __init__(self, url: str):
        if not is_valid_url(url): raise ValueError("Invalid URL")
        self.url = url
        self.domain = urlparse(url).netloc
        self.status_code, self.content, self.latency, self.headers = safe_request(url)
        self.html = self.content.decode(errors="ignore") if self.content else ""
        self.links_internal, self.links_external = [], []
        self.resources_css, self.resources_js, self.resources_img = [], [], []
        self._extract()

    def _extract(self):
        hrefs = re.findall(r'href=[\'"]?([^\'" >]+)', self.html, flags=re.IGNORECASE)
        srcs = re.findall(r'src=[\'"]?([^\'" >]+)', self.html, flags=re.IGNORECASE)
        for u in hrefs:
            full = urljoin(self.url, u)
            if urlparse(full).netloc == self.domain:
                self.links_internal.append(full)
            else:
                self.links_external.append(full)
        for s in srcs:
            full = urljoin(self.url, s)
            if full.lower().endswith(".css"): self.resources_css.append(full)
            elif full.lower().endswith(".js"): self.resources_js.append(full)
            elif any(full.lower().endswith(ext) for ext in(".png",".jpg",".jpeg",".webp",".gif",".svg")):
                self.resources_img.append(full)

    def compute_metrics(self) -> Dict[int, Dict[str, Any]]:
        m: Dict[int, Dict[str, Any]] = {}
        total_errors = total_warnings = total_notices = 0

        # Status
        m[2] = {"value": "Pending", "detail": "Website Grade"}
        m[7] = {"value": {"errors": 0,"warnings":0,"notices":0}, "detail": "Severity"}
        m[21] = {"value": 1 if 200 <= self.status_code < 300 else 0, "detail": f"Status {self.status_code}"}
        m[23] = {"value": 1 if 400 <= self.status_code < 500 else 0, "detail": f"Status {self.status_code}"}
        m[24] = {"value": 1 if 500 <= self.status_code < 600 else 0, "detail": f"Status {self.status_code}"}
        if m[23]["value"] or m[24]["value"]: total_errors += 1

        # Title/meta
        title_match = re.search(r"<title>(.*?)</title>", self.html, flags=re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""
        meta_desc_match = re.search(r'<meta[^>]+name=["\']description["\'][^>]*content="\'["\']', self.html, flags=re.IGNORECASE)
        meta_desc = meta_desc_match.group(1).strip() if meta_desc_match else ""

        m[41] = {"value": 1 if not title else 0, "detail": "Missing title"}
        m[43] = {"value": 1 if title and len(title) > 65 else 0, "detail": f"Title length {len(title) if title else 0}"}
        m[44] = {"value": 1 if title and len(title) < 15 else 0, "detail": f"Title length {len(title) if title else 0}"}
        m[45] = {"value": 1 if not meta_desc else 0, "detail": "Missing meta description"}
        m[47] = {"value": 1 if meta_desc and len(meta_desc) > 165 else 0, "detail": f"Meta length {len(meta_desc) if meta_desc else 0}"}
        m[48] = {"value": 1 if meta_desc and len(meta_desc) < 50 else 0, "detail": f"Meta length {len(meta_desc) if meta_desc else 0}"}
        total_errors += 1 if m[41]["value"] else 0
        total_warnings += (m[43]["value"] or m[44]["value"] or m[45]["value"])
        total_notices += (m[47]["value"] or m[48]["value"])

        # H1 / images
        h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", self.html, flags=re.IGNORECASE | re.DOTALL)
        m[49] = {"value": 1 if len(h1s) == 0 else 0, "detail": f"H1 count {len(h1s)}"}
        m[50] = {"value": 1 if len(h1s) > 1 else 0, "detail": f"H1 count {len(h1s)}"}
        total_warnings += (m[49]["value"] or m[50]["value"])

        img_tags = re.findall(r"<img[^>]*>", self.html, flags=re.IGNORECASE)
        missing_alts = sum(1 for tag in img_tags if re.search(r'alt=["\'].*?["\']', tag, flags=re.IGNORECASE) is None)
        m[55] = {"value": missing_alts, "detail": f"Images missing alt: {missing_alts}"}
        total_notices += 1 if missing_alts > 0 else 0

        # URL / HTTPS / security
        m[63] = {"value": 1 if len(self.url) > 115 else 0, "detail": f"URL length {len(self.url)}"}
        m[64] = {"value": 1 if re.search(r"[A-Z]", self.url) else 0, "detail": "Uppercase in URL" if re.search(r"[A-Z]", self.url) else "Lowercase"}
        is_https = self.url.startswith("https://")
        m[105] = {"value": 1 if is_https else 0, "detail": "HTTPS enabled" if is_https else "Not HTTPS"}
        total_errors += 0 if is_https else 1
        mixed = any(link.startswith("http://") for link in self.links_internal + self.resources_js + self.resources_css + self.resources_img) and is_https
        m[108] = {"value": 1 if mixed else 0, "detail": "Mixed content detected" if mixed else "No mixed content"}
        total_warnings += 1 if mixed else 0

        # Viewport / canonical / social
        viewport_meta = re.search(r'<meta[^>]+name=["\']viewport["\']', self.html, flags=re.IGNORECASE)
        m[98] = {"value": 1 if bool(viewport_meta) else 0, "detail": "Viewport meta present" if viewport_meta else "Missing viewport"}
        total_warnings += 0 if viewport_meta else 1
        canonical = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]*href="\'["\']', self.html, flags=re.IGNORECASE)
        m[32] = {"value": 0 if canonical else 1, "detail": f"Canonical present: {bool(canonical)}"}
        og_or_twitter = bool(re.search(r'property=["\']og:', self.html) or re.search(r'name=["\']twitter:', self.html))
        m[62] = {"value": 0 if og_or_twitter else 1, "detail": "Open Graph/Twitter present" if og_or_twitter else "Missing"}

        # robots/sitemap
        robots_url = f"{urlparse(self.url).scheme}://{self.domain}/robots.txt"
        rcode, rcontent, _, _ = safe_request(robots_url)
        m[29] = {"value": 0 if rcode == 200 and rcontent else 1, "detail": "robots.txt present" if rcode == 200 else "robots.txt missing"}
        sitemap_present = False
        for path in ["/sitemap.xml","/sitemap_index.xml","/sitemap"]:
            scode, scontent, _, _ = safe_request(f"{urlparse(self.url).scheme}://{self.domain}{path}")
            if scode == 200 and scontent: sitemap_present = True; break
        m[136] = {"value": 1 if sitemap_present else 0, "detail": "Sitemap present" if sitemap_present else "Sitemap missing"}

        # Performance basics
        page_size_kb = len(self.content)/1024 if self.content else 0
        m[84] = {"value": round(page_size_kb,2), "detail": f"Total page size KB {round(page_size_kb,2)}"}
        m[85] = {"value": len(self.resources_css)+len(self.resources_js)+len(self.resources_img), "detail": "Requests per page (approx)"}
        m[91] = {"value": round(self.latency*1000,2), "detail": f"Server response ms {round(self.latency*1000,2)}"}
        cache_control = (self.headers.get("Cache-Control") or "")
        m[94] = {"value": 0 if "max-age" in cache_control.lower() else 1, "detail": f"Cache-Control: {cache_control}"}
        content_encoding = (self.headers.get("Content-Encoding") or "").lower()
        compressed = any(enc in content_encoding for enc in ["gzip","br"])
        m[95] = {"value": 1 if compressed else 0, "detail": f"Content-Encoding: {content_encoding or 'none'}"}
        rb_css = len(self.resources_css)
        rb_js_sync = len(self.resources_js)
        m[88] = {"value": rb_css + rb_js_sync, "detail": f"Potential render-blocking (approx): {rb_css+rb_js_sync}"}
        dom_nodes = len(re.findall(r"<[a-zA-Z]+", self.html))
        m[89] = {"value": dom_nodes, "detail": f"Approx DOM nodes {dom_nodes}"}
        third_js = sum(1 for js in self.resources_js if urlparse(js).netloc != self.domain)
        m[90] = {"value": third_js, "detail": f"3rd-party scripts {third_js}"}
        large_imgs = sum(1 for img in self.resources_img if re.search(r"(large|hero|banner|@2x|\d{4}x\d{4})", img, flags=re.IGNORECASE))
        m[92] = {"value": large_imgs, "detail": "Potentially unoptimized images (heuristic)"}
        lazy_count = len(re.findall(r'loading=["\']lazy["\']', self.html, flags=re.IGNORECASE))
        m[93] = {"value": 0 if lazy_count>0 else 1, "detail": f"Lazy loading tags count {lazy_count}"}

        # Security headers
        sec_required = ["Content-Security-Policy","Strict-Transport-Security","X-Frame-Options","X-Content-Type-Options","Referrer-Policy"]
        missing_sec = [h for h in sec_required if h not in self.headers]
        m[110] = {"value": len(missing_sec), "detail": f"Missing security headers: {missing_sec}"}

        # Broken links sample
        broken_internal = 0
        for li in self.links_internal[:20]:
            code, _, _, _ = safe_request(li)
            if code >= 400 or code == 0: broken_internal += 1
        broken_external = 0
        for le in self.links_external[:20]:
            code, _, _, _ = safe_request(le)
            if code >= 400 or code == 0: broken_external += 1
        m[27] = {"value": broken_internal, "detail": "Broken internal links (sample)"}
        m[28] = {"value": broken_external, "detail": "Broken external links (sample)"}

        # Category scoring
        cat_scores = {
            "Crawlability": max(0, 100 - (m[27]["value"] + m[28]["value"])*5),
            "On-Page SEO": max(0, 100 - (m[41]["value"] + m[45]["value"] + m[43]["value"] + m[44]["value"])*10),
            "Performance": max(0, 100 - (m[84]["value"]/10 + m[88]["value"]*5 + (0 if m[95]["value"] else 10))),
            "Security": max(0, 100 - (m[110]["value"]*10 + (0 if m[105]["value"] else 50))),
            "Mobile": max(0, 100 - (0 if m[98]["value"]==1 else 30)),
        }
        m[8] = {"value": cat_scores, "detail": "Category score breakdown"}
        m[7] = {"value": {"errors": total_errors, "warnings": total_warnings, "notices": total_notices}, "detail": "Severity"}

        # Overall score and grade
        base = 100
        base -= (10 if m[41]["value"] else 0)       # missing title
        base -= (5 if m[45]["value"] else 0)        # missing meta
        base -= (15 if m[105]["value"]==0 else 0)   # no https
        base -= min(10, m[88]["value"])             # render-blocking approx
        base -= min(8, int((len(self.content)/1024)/512)*2 if self.content else 0)
        score = max(0, min(100, base))
        m[1] = {"value": score, "detail": "Overall Site Health (%)"}
        m[2] = {"value": grade_from_score(score), "detail": "Website Grade"}

        # Executive summary + strengths/weaknesses
        strengths, weaknesses, priority_fixes = [], [], []
        if m[105]["value"]: strengths.append("HTTPS enabled")
        if title and 15 <= len(title) <= 65: strengths.append("Title length optimal")
        if meta_desc and 50 <= len(meta_desc) <= 165: strengths.append("Meta description optimal")
        if lazy_count > 0: strengths.append("Lazy loading used")
        if m[95]["value"]: strengths.append("Compression (gzip/br) enabled")

        if m[41]["value"]: weaknesses.append("Missing title")
        if m[45]["value"]: weaknesses.append("Missing meta description")
        if m[110]["value"] > 0: weaknesses.append("Missing security headers")
        if m[27]["value"] > 0: weaknesses.append("Broken internal links")
        if m[136]["value"] == 0: weaknesses.append("Missing sitemap")

        if m[27]["value"] > 0: priority_fixes.append("Fix internal broken links")
        if m[105]["value"] == 0: priority_fixes.append("Enable HTTPS sitewide")
        if m[110]["value"] > 0: priority_fixes.append("Implement CSP, HSTS, X-Frame-Options, etc.")
        if m[98]["value"] == 0: priority_fixes.append("Add responsive viewport meta")
        if not m[95]["value"] and m[84]["value"] > 256: priority_fixes.append("Enable gzip/brotli compression")

        m[4] = {"value": strengths, "detail": "Strengths"}
        m[5] = {"value": weaknesses, "detail": "Weak areas"}
        m[6] = {"value": priority_fixes, "detail": "Priority fixes"}

        # extras
        m[175] = {"value": min(100, (broken_internal*10)+(broken_external*5)), "detail": "Fix priority (heuristic)"}
        m[180] = {"value": min(100, ((1 if m[23]['value'] else 0)+(1 if m[24]['value'] else 0))*30 + m[110]["value"]*10), "detail": "Risk severity (heuristic)"}
        m[182] = {"value": max(0, 100 - (m[110]["value"]*10 + m[88]["value"]*5)), "detail": "Quick wins"}
        m[189] = {"value": min(100, m[88]["value"]*5 + m[92]["value"]*5), "detail": "Speed improvement potential"}
        m[191] = {"value": min(100, m[110]["value"]*10), "detail": "Security improvement potential"}
        m[200] = {"value": max(0, 100 - m[180]["value"]), "detail": "Growth readiness"}

        # Summary text
        m[3] = {"value": self.executive_summary(m), "detail": "Executive Summary (~200 words)"}

        # Fill missing IDs
        for pid in range(1, 201):
            if pid not in m:
                m[pid] = {"value": "N/A", "detail": "Not computed in quick audit"}

        return m

    def executive_summary(self, metrics: Dict[int, Dict[str, Any]]) -> str:
        score = metrics[1]["value"]; grade = metrics[2]["value"]
        sev = metrics[7]["value"]; perf = metrics[84]["value"]; resp = metrics[91]["value"]
        strengths = ", ".join(metrics[4]["value"]) if metrics[4]["value"] else "None"
        weaknesses = ", ".join(metrics[5]["value"]) if metrics[5]["value"] else "None"
        text = (
            f"{APP_BRAND} audited {self.url} across crawlability, on-page SEO, performance, mobile, and security. "
            f"Overall health score is {score}% ({grade}). We found {sev['errors']} errors, {sev['warnings']} warnings, {sev['notices']} notices. "
            f"Approx payload {perf} KB; server response {resp} ms. Strengths: {strengths}. Weaknesses: {weaknesses}. "
            f"Priority: link integrity, HTTPS/security headers, responsive meta, compression."
        )
        return text
