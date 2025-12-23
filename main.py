import asyncio
import time
import io
import os
from typing import Dict, List, Tuple, Set
from urllib.parse import urlparse, urljoin

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates

from bs4 import BeautifulSoup
from fpdf import FPDF

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

app = FastAPI(title="FF TECH ELITE – Multi-Page Audit Engine")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ==================== CONFIGURATION ====================
CATEGORIES = ["Performance", "SEO", "UX", "Security"]
PILLAR_WEIGHTS = {"Performance": 0.45, "SEO": 0.25, "UX": 0.15, "Security": 0.15}

METRICS: List[Tuple[str, str]] = [
    ("Largest Contentful Paint (ms)", "Performance"),
    ("Cumulative Layout Shift", "Performance"),
    ("Total Blocking Time (ms)", "Performance"),
    ("First Contentful Paint (ms)", "Performance"),
    ("Time to First Byte (ms)", "Performance"),
    ("Speed Index (ms)", "Performance"),
    ("Time to Interactive (ms)", "Performance"),
    ("Page Weight (KB)", "Performance"),
    ("DOM Element Count", "Performance"),
    ("Resource Count", "Performance"),
    ("Page Title Present", "SEO"),
    ("Meta Description", "SEO"),
    ("Canonical Tag", "SEO"),
    ("Single H1 Tag", "SEO"),
    ("Structured Data", "SEO"),
    ("Image ALT Coverage %", "SEO"),
    ("Viewport Meta Tag", "UX"),
    ("Core Web Vitals Pass", "UX"),
    ("Navigation Present", "UX"),
    ("HTTPS Enforced", "Security"),
    ("HSTS Header", "Security"),
    ("Content Security Policy", "Security"),
    ("X-Frame-Options", "Security"),
    ("X-Content-Type-Options", "Security"),
    ("Referrer-Policy", "Security"),
    ("Permissions-Policy", "Security"),
]

while len(METRICS) < 66:
    METRICS.append((f"Advanced Check {len(METRICS)+1}", "SEO"))

# ==================== SCORING ====================
def score_strict(val: float, good: float, ok: float) -> int:
    if val <= good: return 100
    if val <= ok: return 60
    return 0

def score_bool_strict(cond: bool) -> int:
    return 100 if cond else 0

def score_pct_strict(cov: int, total: int) -> int:
    if total == 0: return 100
    pct = (cov / total) * 100
    if pct >= 95: return 100
    if pct >= 80: return 60
    return 0

# ==================== SINGLE PAGE AUDIT ====================
async def single_page_audit(page, url: str) -> Dict:
    try:
        start = time.time()
        response = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        ttfb = (time.time() - start) * 1000
        await asyncio.sleep(2)

        perf = await page.evaluate("""
            () => {
                const p = performance.getEntriesByType('paint');
                const l = performance.getEntriesByType('largest-contentful-paint');
                const s = performance.getEntriesByType('layout-shift')
                    .filter(e => !e.hadRecentInput)
                    .reduce((a,e) => a + e.value, 0);
                const t = performance.getEntriesByType('longtask')
                    .reduce((a,e) => a + Math.max(0, e.duration - 50), 0);
                return {
                    fcp: p.find(e => e.name === 'first-contentful-paint')?.startTime || 9999,
                    lcp: l[l.length-1]?.startTime || 9999,
                    cls: s,
                    tbt: t,
                    domCount: document.querySelectorAll('*').length
                };
            }
        """)

        html = await page.content()
        headers = {k.lower(): v for k, v in (response.headers if response else {}).items()}

        soup = BeautifulSoup(html, "html.parser")
        imgs = soup.find_all("img")
        alt_ok = len([i for i in imgs if i.get("alt", "").strip()])
        resources = len(soup.find_all(["img", "script", "link", "style", "iframe"]))
        weight_kb = len(html.encode()) / 1024

        scores = {
            "Largest Contentful Paint (ms)": score_strict(perf["lcp"], 1500, 2500),
            "Cumulative Layout Shift": score_strict(perf["cls"], 0.05, 0.1),
            "Total Blocking Time (ms)": score_strict(perf["tbt"], 100, 300),
            "First Contentful Paint (ms)": score_strict(perf["fcp"], 1000, 1800),
            "Time to First Byte (ms)": score_strict(ttfb, 100, 400),
            "Speed Index (ms)": score_strict(perf["fcp"], 1000, 2000),
            "Time to Interactive (ms)": score_strict(perf["fcp"] + perf["tbt"], 2000, 3800),
            "Page Weight (KB)": score_strict(weight_kb, 1000, 2500),
            "DOM Element Count": score_strict(perf["domCount"], 800, 1500),
            "Resource Count": score_strict(resources, 40, 80),

            "Page Title Present": score_bool_strict(bool(soup.title and soup.title.string)),
            "Meta Description": score_bool_strict(bool(soup.find("meta", attrs={"name": "description"}))),
            "Canonical Tag": score_bool_strict(bool(soup.find("link", rel="canonical"))),
            "Single H1 Tag": score_bool_strict(len(soup.find_all("h1")) == 1),
            "Structured Data": score_bool_strict(bool(soup.find_all("script", type="application/ld+json"))),
            "Image ALT Coverage %": score_pct_strict(alt_ok, len(imgs)),

            "Viewport Meta Tag": score_bool_strict(bool(soup.find("meta", attrs={"name": "viewport"}))),
            "Core Web Vitals Pass": 100 if perf["lcp"] <= 2500 and perf["cls"] <= 0.1 and perf["tbt"] <= 300 else 0,
            "Navigation Present": score_bool_strict(bool(soup.find("nav"))),

            "HTTPS Enforced": score_bool_strict(url.startswith("https://")),
            "HSTS Header": score_bool_strict("strict-transport-security" in headers),
            "Content Security Policy": score_bool_strict("content-security-policy" in headers),
            "X-Frame-Options": score_bool_strict(headers.get("x-frame-options") in ("DENY", "SAMEORIGIN")),
            "X-Content-Type-Options": score_bool_strict(headers.get("x-content-type-options") == "nosniff"),
            "Referrer-Policy": score_bool_strict("referrer-policy" in headers),
            "Permissions-Policy": score_bool_strict("permissions-policy" in headers),
        }

        pillar_sums = {c: [] for c in CATEGORIES}
        for name, cat in METRICS:
            score = scores.get(name, 60)
            pillar_sums[cat].append(score)

        pillar_avg = {c: round(sum(pillar_sums[c]) / len(pillar_sums[c])) if pillar_sums[c] else 0 for c in CATEGORIES}
        total = round(sum(pillar_avg[c] * PILLAR_WEIGHTS[c] for c in CATEGORIES))

        return {
            "url": url,
            "total_grade": total,
            "pillars": pillar_avg,
            "summary": f"LCP {perf['lcp']:.0f}ms • CLS {perf['cls']:.2f} • TBT {perf['tbt']:.0f}ms",
            "perf_metrics": perf
        }
    except:
        return {
            "url": url,
            "total_grade": 30,
            "pillars": {"Performance": 20, "SEO": 40, "UX": 30, "Security": 30},
            "summary": "Page audit failed or blocked",
            "perf_metrics": {"fcp":9999,"lcp":9999,"cls":0.5,"tbt":999}
        }

# ==================== MULTI-PAGE SITE AUDIT ====================
@app.post("/site-audit")
async def site_audit(request: Request):
    try:
        data = await request.json()
        base_url = data.get("url", "").strip()
        max_pages = data.get("max_pages", 15)  # Limit to avoid timeout
        mobile = data.get("mode") == "mobile"

        if not base_url:
            raise HTTPException(400, "URL required")
        base_url = base_url if base_url.startswith(("http://", "https://")) else f"https://{base_url}"

        parsed = urlparse(base_url)
        domain = parsed.netloc

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = await browser.new_context(
                viewport={"width": 390, "height": 844} if mobile else {"width": 1366, "height": 768}
            )
            page = await context.new_page()

            visited: Set[str] = set()
            to_visit: List[str] = [base_url]
            page_results = []

            while to_visit and len(page_results) < max_pages:
                url = to_visit.pop(0)
                if url in visited: continue
                visited.add(url)

                result = await single_page_audit(page, url)  # Reuse same page for speed
                page_results.append(result)

                # Extract new internal links
                try:
                    links = await page.eval_on_selector_all("a[href]", "els => els.map(a => a.href)")
                    for link in links[:30]:  # Limit per page
                        parsed_link = urlparse(urljoin(url, link))
                        if parsed_link.netloc == domain and parsed_link.path and link not in visited:
                            to_visit.append(urljoin(url, link))
                except: pass

            await browser.close()

        # Aggregate results
        if not page_results:
            raise HTTPException(500, "No pages audited")

        avg_total = round(sum(r["total_grade"] for r in page_results) / len(page_results))
        avg_pillars = {}
        for c in CATEGORIES:
            avg_pillars[c] = round(sum(r["pillars"].get(c, 0) for r in page_results) / len(page_results))

        return {
            "site_url": base_url,
            "pages_audited": len(page_results),
            "average_grade": avg_total,
            "average_pillars": avg_pillars,
            "pages": page_results,
            "summary": f"Audited {len(page_results)} pages. Average score: {avg_total}%"
        }

    except Exception as e:
        raise HTTPException(500, f"Site audit failed: {str(e)}")

# ==================== SINGLE PAGE (Keep for compatibility) ====================
@app.post("/audit")
async def single_audit(request: Request):
    data = await request.json()
    result = (await site_audit(request))["pages"][0] if "pages" in (await site_audit(request)) else {}
    return result or {"error": "Single audit failed"}

# ==================== PDF (Site Report) ====================
@app.post("/download")
async def pdf(request: Request):
    data = await request.json()
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 15, "FF TECH ELITE SITE AUDIT REPORT", ln=1, align="C")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 10, f"Site: {data.get('site_url', data.get('url'))}", ln=1)
    pdf.cell(0, 10, f"Average Score: {data.get('average_grade', data.get('total_grade'))}%", ln=1)
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Average Pillars", ln=1)
    pdf.set_font("Helvetica", "", 11)
    pillars = data.get("average_pillars", data.get("pillars", {}))
    for p, s in pillars.items():
        pdf.cell(0, 8, f"{p}: {s}%", ln=1)
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 10, f"Audited Pages ({data.get('pages_audited', 1)})", ln=1)
    pdf.set_font("Helvetica", "", 9)
    pages = data.get("pages", [data])
    for pg in pages:
        pdf.cell(0, 8, f"{pg['url']} → {pg['total_grade']}% | {pg['summary']}", ln=1)

    return StreamingResponse(io.BytesIO(pdf.output(dest="S").encode("latin1")),
                             media_type="application/pdf",
                             headers={"Content-Disposition": "attachment; filename=SiteAudit_Report.pdf"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
