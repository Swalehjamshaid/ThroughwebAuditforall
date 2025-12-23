import time, io, json, math, re, subprocess, tempfile, os
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
from fpdf import FPDF

# =====================================================
# APP SETUP
# =====================================================

app = FastAPI(title="FF TECH ELITE – Top 1% Real Audit Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# HELPERS
# =====================================================

def normalize_url(url):
    return url if url.startswith("http") else f"https://{url}"

def clamp(v):
    return max(0, min(100, int(v)))

def score_bool(v):
    return 100 if v else 0

# ---------------- WCAG CONTRAST MATH ----------------

def _lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

def luminance(rgb):
    r, g, b = rgb
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)

def contrast_ratio(fg, bg):
    L1 = luminance(fg) + 0.05
    L2 = luminance(bg) + 0.05
    return max(L1, L2) / min(L1, L2)

# ---------------- CVSS STYLE ----------------

CVSS = {
    "low": 2.0,
    "medium": 5.0,
    "high": 7.5,
    "critical": 9.8
}

# =====================================================
# LIGHTHOUSE JSON PARITY (REAL)
# =====================================================

def run_lighthouse(url, mode):
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "lh.json")
        cmd = [
            "lighthouse",
            url,
            "--output=json",
            f"--output-path={out}",
            "--quiet",
            "--chrome-flags=--headless"
        ]
        if mode == "mobile":
            cmd.append("--preset=mobile")
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return json.load(open(out))

# =====================================================
# CORE AUDIT ENGINE
# =====================================================

async def run_audit(url, mode):
    metrics = []
    issues = []

    # ---------------- REAL BROWSER ----------------
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            viewport={"width": 375, "height": 812} if mode == "mobile" else {"width": 1440, "height": 900}
        )
        page = await context.new_page()
        await page.goto(url, wait_until="networkidle", timeout=60000)
        html = await page.content()
        await browser.close()

    soup = BeautifulSoup(html, "html.parser")

    # =================================================
    # PERFORMANCE – LIGHTHOUSE PARITY
    # =================================================

    lh = run_lighthouse(url, mode)
    audits = lh["audits"]

    perf_score = round(lh["categories"]["performance"]["score"] * 100)

    def lh_metric(key, name):
        val = audits[key].get("numericValue", 0)
        score = clamp(100 - (val / 50))
        metrics.append({"name": name, "category": "Performance", "score": score})

    lh_metric("largest-contentful-paint", "Largest Contentful Paint")
    lh_metric("cumulative-layout-shift", "Cumulative Layout Shift")
    lh_metric("total-blocking-time", "Total Blocking Time")

    # =================================================
    # SEO + FIX SUGGESTIONS
    # =================================================

    def seo(cond, name, fix):
        score = score_bool(cond)
        if not cond:
            issues.append({"type": "SEO", "issue": name, "fix": fix})
        metrics.append({"name": name, "category": "SEO", "score": score})

    seo(soup.title and 15 <= len(soup.title.text) <= 60,
        "Title Tag Length",
        "Use a unique 50–60 character <title>.")

    seo(soup.find("meta", {"name": "description"}),
        "Meta Description",
        "Add a compelling meta description.")

    seo(len(soup.find_all("h1")) == 1,
        "Single H1",
        "Ensure exactly one H1 per page.")

    seo(requests.get(url + "/robots.txt", timeout=10).status_code == 200,
        "robots.txt",
        "Create a robots.txt file.")

    seo(requests.get(url + "/sitemap.xml", timeout=10).status_code == 200,
        "sitemap.xml",
        "Generate and submit sitemap.xml.")

    # =================================================
    # ACCESSIBILITY – WCAG 2.1 AA / AAA
    # =================================================

    imgs = soup.find_all("img")
    alt_ok = sum(1 for i in imgs if i.get("alt"))

    metrics.append({
        "name": "Image ALT Coverage",
        "category": "Accessibility",
        "score": clamp((alt_ok / len(imgs)) * 100 if imgs else 100)
    })

    contrast_fail = 0
    for el in soup.find_all(text=True):
        parent = el.parent
        if parent.name in ["script", "style"]:
            continue
        style = parent.get("style", "")
        fg = re.findall(r"color:\s*rgb\((\d+),(\d+),(\d+)\)", style)
        bg = re.findall(r"background.*rgb\((\d+),(\d+),(\d+)\)", style)
        if fg and bg:
            ratio = contrast_ratio(tuple(map(int, fg[0])), tuple(map(int, bg[0])))
            if ratio < 4.5:
                contrast_fail += 1

    if contrast_fail:
        issues.append({
            "type": "Accessibility",
            "issue": "Low color contrast",
            "fix": "Ensure text contrast ≥ 4.5:1 (WCAG AA)."
        })

    metrics.append({
        "name": "Color Contrast (WCAG AA)",
        "category": "Accessibility",
        "score": clamp(100 - contrast_fail * 10)
    })

    # =================================================
    # SECURITY – CVSS STYLE SCORING
    # =================================================

    headers = requests.get(url, timeout=10).headers
    sec_risk = 0

    def sec(cond, name, severity, fix):
        nonlocal sec_risk
        if not cond:
            sec_risk += CVSS[severity]
            issues.append({
                "type": "Security",
                "issue": name,
                "severity": severity,
                "fix": fix
            })
        metrics.append({"name": name, "category": "Security", "score": score_bool(cond)})

    sec(urlparse(url).scheme == "https",
        "HTTPS",
        "critical",
        "Force HTTPS site-wide.")

    sec("strict-transport-security" in headers,
        "HSTS Header",
        "high",
        "Add Strict-Transport-Security header.")

    sec("content-security-policy" in headers,
        "Content Security Policy",
        "high",
        "Define a strict Content-Security-Policy.")

    security_score = clamp(100 - sec_risk * 5)

    # =================================================
    # PILLARS
    # =================================================

    def pillar(cat):
        s = [m["score"] for m in metrics if m["category"] == cat]
        return round(sum(s) / len(s)) if s else 100

    pillars = {
        "Performance": perf_score,
        "SEO": pillar("SEO"),
        "Accessibility": pillar("Accessibility"),
        "Security": security_score,
        "UX": round((perf_score + pillar("Accessibility")) / 2)
    }

    total = round(sum(pillars.values()) / len(pillars))

    return {
        "url": url,
        "total_grade": total,
        "pillars": pillars,
        "metrics": metrics,
        "issues": issues,
        "summary": (
            "Audit uses real Chromium, Google Lighthouse JSON parity, "
            "WCAG 2.1 AA contrast math, SEO issue detection with fixes, "
            "and CVSS-style security risk scoring."
        )
    }

# =====================================================
# API ENDPOINTS
# =====================================================

@app.post("/audit")
async def audit(req: Request):
    body = await req.json()
    return await run_audit(normalize_url(body["url"]), body.get("mode", "desktop"))

@app.post("/download")
async def download(data: dict):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)

    pdf.cell(0, 10, "FF TECH ELITE – Enterprise Audit Report", ln=True)
    pdf.cell(0, 10, f"URL: {data['url']}", ln=True)
    pdf.cell(0, 10, f"Overall Score: {data['total_grade']}%", ln=True)
    pdf.ln(5)

    pdf.cell(0, 10, "Detected Issues & Fixes:", ln=True)
    for i in data.get("issues", []):
        pdf.multi_cell(0, 8, f"- [{i['type']}] {i['issue']} → FIX: {i['fix']}")

    stream = io.BytesIO(pdf.output(dest="S").encode("latin1"))
    return StreamingResponse(stream, media_type="application/pdf")
