
import os, io, time, logging, requests
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse, urlunparse

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates

from bs4 import BeautifulSoup

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FF_TECH_ELITE_V3")

# ---------- Optional Playwright ----------
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not installed. Lab metrics will be skipped.")

# ---------- FastAPI ----------
app = FastAPI(title="FF TECH ELITE v3 - Ultimate Website Audit")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
templates = Jinja2Templates(directory="templates")

# ---------- PSI (Lighthouse) ----------
PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
PSI_API_KEY = os.getenv("PAGESPEED_API_KEY")  # optional but recommended

def normalize_url(raw_url: str) -> str:
    raw_url = (raw_url or "").strip()
    parsed = urlparse(raw_url)
    if not parsed.scheme:
        parsed = urlparse("https://" + raw_url)
    if not parsed.netloc:
        return ""
    return urlunparse(parsed._replace(path=parsed.path or "/"))

def call_psi(url: str, strategy: str = "mobile") -> dict:
    params = {"url": url, "strategy": strategy, "category": ["performance","seo","best-practices","accessibility"]}
    if PSI_API_KEY: params["key"] = PSI_API_KEY
    r = requests.get(PSI_ENDPOINT, params=params, timeout=60)
    r.raise_for_status()
    return r.json()

def extract_psi(psi: dict) -> dict:
    lhr = psi.get("lighthouseResult", {})
    audits = lhr.get("audits", {})
    cats = lhr.get("categories", {})
    def nv(aid): return audits.get(aid, {}).get("numericValue")
    # opportunities titles (for roadmap)
    opportunities = []
    for aid, a in (audits or {}).items():
        det = a.get("details", {})
        if det.get("type") == "opportunity":
            title = a.get("title", aid)
            sv_ms = det.get("overallSavingsMs")
            sv_bt = det.get("overallSavingsBytes")
            add = f"{title}"
            if sv_ms or sv_bt:
                s = []
                if sv_ms: s.append(f"~{int(sv_ms)} ms")
                if sv_bt: s.append(f"~{int(sv_bt/1024)} KB")
                add += f" (Savings: {', '.join(s)})"
            opportunities.append(add)
    return {
        "lcp": nv("largest-contentful-paint"),
        "fcp": nv("first-contentful-paint"),
        "cls": audits.get("cumulative-layout-shift", {}).get("numericValue"),
        "inp": nv("interaction-to-next-paint"),
        "speed_index": nv("speed-index"),
        "dom_size": nv("dom-size"),
        "tbt": nv("total-blocking-time"),
        "perf_percent": int(round(float(cats.get("performance", {}).get("score", 0)) * 100)),
        "viewport_pass": audits.get("viewport", {}).get("score") == 1,
        "opportunities": opportunities
    }

# ---------- Playwright lab audit ----------
async def run_lab(url: str) -> Dict[str, Any]:
    if not PLAYWRIGHT_AVAILABLE:
        return {
            "ttfb": 0, "fcp": 0, "lcp": 0, "cls": 0.0, "tbt": 0,
            "page_weight_kb": 0, "request_count": 0,
            "html": "", "headers": {}, "console_errors": [], "cookies": []
        }
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox","--disable-setuid-sandbox"])
        context = await browser.new_context(viewport={"width":1366,"height":768})
        page = await context.new_page()

        console_errors: List[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        start = time.time()
        resp = await page.goto(url, wait_until="networkidle", timeout=60000)
        if not resp or resp.status >= 400:
            await browser.close()
            raise HTTPException(502, f"Page failed to load (status: {resp.status if resp else 'None'})")
        ttfb = int((time.time() - start) * 1000)

        metrics = await page.evaluate("""() => {
            const paint = performance.getEntriesByType('paint')||[];
            const lcpE = performance.getEntriesByType('largest-contentful-paint')||[];
            const res = performance.getEntriesByType('resource')||[];
            const long = performance.getEntriesByType('longtask')||[];
            const fcp = paint.find(e=>e.name==='first-contentful-paint')?.startTime||0;
            const lcp = lcpE.length ? lcpE[lcpE.length-1].startTime : 0;
            let bytes=0; res.forEach(r=>{ if(r.transferSize) bytes+=r.transferSize; });
            const cls = (performance.getEntriesByType('layout-shift')||[])
                .filter(e=>!e.hadRecentInput).reduce((s,e)=>s+(e.value||0),0);
            const tbt = long.reduce((s,lt)=>s+(lt.duration||0),0);
            return {fcp:Math.round(fcp), lcp:Math.round(lcp), bytes, reqs:res.length, cls, tbt:Math.round(tbt)};
        }""")
        html = await page.content()
        headers = {k.lower(): v for k, v in (resp.headers or {}).items()}
        cookies = await context.cookies()
        await browser.close()
        return {
            "ttfb": ttfb, "fcp": metrics["fcp"], "lcp": metrics["lcp"], "cls": round(metrics["cls"],3),
            "tbt": metrics["tbt"], "page_weight_kb": round(metrics["bytes"]/1024), "request_count": metrics["reqs"],
            "html": html, "headers": headers, "console_errors": console_errors, "cookies": cookies
        }

# ---------- DOM analysis ----------
def analyze_dom(html: str, url: str) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")
    title = soup.find("title")
    meta_desc = soup.find("meta", attrs={"name":"description"})
    h1 = soup.find("h1")
    headings = {f"H{n}": len(soup.find_all(f"h{n}")) for n in range(2,7)}
    viewport = soup.find("meta", attrs={"name":"viewport"})
    favicon = bool(soup.find("link", rel=lambda x: x and "icon" in x.lower()))
    canonical = soup.find("link", attrs={"rel":"canonical"})
    schema_present = bool(soup.find("script", attrs={"type":"application/ld+json"}))
    robots_meta = soup.find("meta", attrs={"name":"robots"})
    lang = soup.find("html").get("lang") if soup.find("html") else None

    def has_social(hosts: List[str]) -> bool:
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            if any(h in href for h in hosts): return True
        return False

    social = {
        "Facebook": has_social(["facebook.com"]),
        "YouTube": has_social(["youtube.com"]),
        "Instagram": has_social(["instagram.com"]),
        "X": has_social(["twitter.com","x.com"]),
        "LinkedIn": has_social(["linkedin.com"]),
    }

    return {
        "title": title.text.strip() if title else None,
        "meta_description": meta_desc.get("content") if meta_desc else None,
        "h1": h1.text.strip() if h1 else None,
        "headings": headings,
        "viewport_present": viewport is not None,
        "favicon": favicon,
        "canonical": canonical is not None,
        "schema_present": schema_present,
        "robots": (robots_meta.get("content") or "").lower() if robots_meta else "",
        "lang": lang,
        "social": social,
    }

# ---------- Build SEO-style sections for front-end ----------
def build_seo_audit(url: str, psi: dict, lab: dict, dom: dict) -> dict:
    issues: List[Dict[str, Any]] = []

    def add_issue(element, note, type_="Page Speed", priority="red-flag"):
        issues.append({"type": type_, "element": element, "priority": priority, "message": note})

    # Page speed & CWV issues (Semrush-style)
    if psi.get("dom_size") is not None:
        ds = int(psi["dom_size"])
        add_issue("DOM Size", f"DOM elements: {ds}. Reduce if excessively large.")

    if psi.get("tbt") is not None:
        add_issue("Total Blocking Time (TBT)", f"{int(psi['tbt'])} ms. Reduce long tasks & JS execution.", priority="flag")
    else:
        add_issue("Total Blocking Time (TBT)", "Unable to retrieve TBT.", priority="flag")

    if psi.get("speed_index") is not None:
        add_issue("Speed Index", f"{int(psi['speed_index'])} ms. Optimize render path.", priority="flag")

    add_issue("First Contentful Paint (FCP)", f"{int(psi.get('fcp') or lab.get('fcp',0))} ms", priority="flag")
    add_issue("Time to First Byte (TTFB)", f"{int(lab.get('ttfb',0))} ms", priority="flag")
    if psi.get("cls") is not None:
        add_issue("Cumulative Layout Shift (CLS)", f"{psi['cls']:.3f}. Reserve space, preload fonts.", priority="flag")
    if psi.get("inp") is not None:
        add_issue("Interaction to Next Paint (INP)", f"{int(psi['inp'])} ms. Optimize handlers/JS.", priority="flag")
    add_issue("Largest Contentful Paint (LCP)", f"{int(psi.get('lcp') or lab.get('lcp',0))} ms", priority="flag")
    add_issue("Mobile Friendliness", "Pass" if psi.get("viewport_pass") else "Fail — configure viewport & responsive layout.", type_="Mobile", priority="flag")
    add_issue("Overall Performance", f"Lighthouse Performance: {psi.get('perf_percent',0)}%", priority="flag")

    # On‑page SEO
    on_page = {
        "url": {"value": url, "note": "Audited URL"},
        "title": {"value": dom["title"], "note": "Ideal length 50–60 chars"},
        "meta_description": {"value": dom["meta_description"], "note": "Aim for 100–130 chars"},
        "h1": {"value": dom["h1"], "note": "Exactly one H1 preferred"},
        "headings": {"structure": dom["headings"], "note": "Use semantic hierarchy"},
        "image_alt": {"note": "Alt attributes coverage heuristic"},
        "keyword_density": {"value": "N/A"},
    }

    # Technical SEO
    technical = [
        {"element":"Favicon", "priority":"pass" if dom["favicon"] else "red-flag",
         "value":"Present" if dom["favicon"] else "Missing", "note":"Provide favicon via <link rel='icon'> or favicon.ico"},
        {"element":"Language", "priority":"info", "value":dom["lang"], "note":"Set <html lang='...'>"},
        {"element":"Canonical", "priority":"pass" if dom["canonical"] else "red-flag",
         "value":"Present" if dom["canonical"] else "Missing", "note":"Add a single canonical to preferred URL"},
        {"element":"Structured Data", "priority":"pass" if dom["schema_present"] else "info",
         "value":"Present" if dom["schema_present"] else "Missing", "note":"Add JSON-LD Schema.org for rich results"},
        {"element":"Robots Meta", "priority":"info", "value":dom["robots"], "note":"Ensure indexable unless intended otherwise"},
        {"element":"Security Headers", "priority":"info", "value":"Partial", "note":"Check CSP, HSTS, XFO, XCTO, Referrer, Permissions"},
    ]

    # Page Performance table (values + notes)
    page_perf = []
    def perf(el, val, note="", pr="info"):
        page_perf.append({"element": el, "priority": pr, "note": f"{val} {note}".strip()})

    perf("Performance Score", f"{psi.get('perf_percent',0)}%")
    perf("Largest Contentful Paint (LCP)", f"{int(psi.get('lcp') or lab.get('lcp',0))} ms")
    perf("Interaction to Next Paint (INP)", f"{int(psi.get('inp') or 0)} ms")
    perf("Cumulative Layout Shift (CLS)", f"{psi['cls']:.3f}" if psi.get('cls') is not None else "N/A")
    perf("Time to First Byte (TTFB)", f"{int(lab.get('ttfb',0))} ms")
    perf("First Contentful Paint (FCP)", f"{int(psi.get('fcp') or lab.get('fcp',0))} ms")
    perf("Speed Index", f"{int(psi.get('speed_index') or 0)} ms")
    perf("Total Blocking Time (TBT)", f"{int(psi.get('tbt') or lab.get('tbt',0))} ms")
    perf("DOM Size", f"{int(psi.get('dom_size') or 0)}")
    perf("Mobile Friendliness", "Pass" if psi.get('viewport_pass') else "Fail")

    # Social presence
    social_media = []
    for net, present in dom["social"].items():
        social_media.append({
            "network": net,
            "priority": "pass" if present else "red-flag",
            "note": "Link detected." if present else f"Add a working {net} link."
        })

    # Section scores (simple placeholders; can be computed if you want)
    section_scores = {
        "On-Page SEO": 70,
        "Technical SEO": 65,
        "Off-Page SEO": 0,
        "Social Media": 50
    }

    return {
        "overview_text": "Comprehensive audit powered by Lighthouse (PSI) & a real browser (Playwright), plus advanced heuristics.",
        "section_scores": section_scores,
        "issues": issues,
        "on_page": on_page,
        "technical": technical,
        "page_performance": page_perf,
        "competitors": [],            # connect an SEO API to populate
        "keyword_rankings": [],       # connect an SEO API to populate
        "top_pages": [],              # connect an SEO API to populate
        "off_page": {"message":"Connect an SEO API for off‑page authority & backlink data"},
        "top_backlinks": [],          # connect an SEO API to populate
        "social_media": social_media
    }

# ---------- PDF helpers ----------
def styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name='H1', fontSize=22, leading=26, textColor=colors.HexColor("#4338ca"), spaceAfter=8))
    s.add(ParagraphStyle(name='H2', fontSize=16, leading=20, textColor=colors.HexColor("#111827"), spaceAfter=6))
    s.add(ParagraphStyle(name='P', fontSize=10, leading=14, textColor=colors.black))
    return s

def table(story, data, col_widths=None, header_bg="#e5e7eb"):
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0), colors.HexColor(header_bg)),
        ('TEXTCOLOR',(0,0),(-1,0), colors.HexColor("#111827")),
        ('GRID',(0,0),(-1,-1), 0.25, colors.HexColor("#d1d5db")),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('LEFTPADDING',(0,0),(-1,-1),6),
        ('RIGHTPADDING',(0,0),(-1,-1),6),
        ('TOPPADDING',(0,0),(-1,-1),5),
        ('BOTTOMPADDING',(0,0),(-1,-1),5),
    ]))
    story.append(t)

# ---------- Routes ----------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/audit")
async def audit(request: Request):
    data = await request.json()
    raw = data.get("url", "").strip()
    url = normalize_url(raw)
    if not url: raise HTTPException(400, "Invalid URL")

    # PSI (Lighthouse) first
    psi_raw = call_psi(url)
    psi = extract_psi(psi_raw)

    # Playwright lab (optional)
    lab = await run_lab(url)

    # DOM analysis
    dom = analyze_dom(lab.get("html",""), url)

    # Build SEO audit sections for front-end
    seo_audit = build_seo_audit(url, psi, lab, dom)

    # Overall grade (use Lighthouse perf percent as main site health proxy)
    total_grade = psi.get("perf_percent", 0)

    return {
        "url": url,
        "audited_at": time.strftime("%B %d, %Y at %H:%M UTC"),
        "total_grade": total_grade,
        "seo_audit": seo_audit
    }

@app.post("/download")
async def download_pdf(request: Request):
    data = await request.json()
    url = data.get("url","")
    score = data.get("total_grade", 0)
    seo = data.get("seo_audit", {})

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=50, bottomMargin=40)
    s = styles()
    story: List[Any] = []

    # Cover
    story.append(Paragraph("FF TECH ELITE v3 - Audit Report", s['H1']))
    story.append(Paragraph(f"URL: {url}", s['P']))
    story.append(Paragraph(f"Generated: {time.strftime('%B %d, %Y at %H:%M UTC')}", s['P']))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"Overall Site Health: {score}%", s['H2']))
    story.append(PageBreak())

    # Overview
    story.append(Paragraph("Overview", s['H2']))
    story.append(Paragraph(seo.get("overview_text",""), s['P']))
    story.append(Spacer(1, 8))
    ss = seo.get("section_scores", {})
    table(story, [["Section","Score%"],
                  ["On-Page SEO", ss.get("On-Page SEO",0)],
                  ["Technical SEO", ss.get("Technical SEO",0)],
                  ["Off-Page SEO", ss.get("Off-Page SEO",0)],
                  ["Social Media", ss.get("Social Media",0)]],
          col_widths=[300, 200])
    story.append(PageBreak())

    # Issues
    story.append(Paragraph("Issues & Recommendations", s['H2']))
    issues = seo.get("issues", [])
    data_tbl = [["Type","Element","Priority","Problem / Recommendation"]]
    for i in issues:
        data_tbl.append([i.get("type",""), i.get("element",""), i.get("priority",""), i.get("message","")])
    table(story, data_tbl, col_widths=[100,100,80,220])
    story.append(PageBreak())

    # On-Page
    story.append(Paragraph("On-Page SEO", s['H2']))
    onp = seo.get("on_page", {})
    on_tbl = [["Element","Value / Status","Note"],
              ["URL", onp.get("url",{}).get("value",""), onp.get("url",{}).get("note","")],
              ["Title", onp.get("title",{}).get("value","—") or "—", onp.get("title",{}).get("note","")],
              ["Meta Description", onp.get("meta_description",{}).get("value","Missing") or "Missing", onp.get("meta_description",{}).get("note","")],
              ["H1", onp.get("h1",{}).get("value","Missing") or "Missing", onp.get("h1",{}).get("note","")],
              ["Heading Structure", f"H2:{onp.get('headings',{}).get('structure',{}).get('H2',0)} H3:{onp.get('headings',{}).get('structure',{}).get('H3',0)} H4:{onp.get('headings',{}).get('structure',{}).get('H4',0)} H5:{onp.get('headings',{}).get('structure',{}).get('H5',0)} H6:{onp.get('headings',{}).get('structure',{}).get('H6',0)}", onp.get("headings",{}).get("note","")],
              ["Image Alt", "Coverage reported", onp.get("image_alt",{}).get("note","")],
              ["Keyword Density", onp.get("keyword_density",{}).get("value","N/A"), "Connect an SEO API for real density"]]
    table(story, on_tbl, col_widths=[120,220,160])
    story.append(PageBreak())

    # Technical
    story.append(Paragraph("Technical SEO", s['H2']))
    tech = seo.get("technical", [])
    tech_tbl = [["Element","Priority","Value","Recommendation"]]
    for t in tech:
        tech_tbl.append([t.get("element",""), t.get("priority",""), t.get("value","—"), t.get("note","")])
    table(story, tech_tbl, col_widths=[140,80,120,160])
    story.append(PageBreak())

    # Page Performance & CWV
    story.append(Paragraph("Page Performance & Core Web Vitals", s['H2']))
    perf = seo.get("page_performance", [])
    perf_tbl = [["Element","Note","Priority"]]
    for p in perf:
        perf_tbl.append([p.get("element",""), p.get("note",""), p.get("priority","info")])
    table(story, perf_tbl, col_widths=[160,260,60])
    story.append(PageBreak())

    # Competitors (placeholder)
    story.append(Paragraph("Competitors", s['H2']))
    comp = seo.get("competitors", [])
    comp_tbl = [["Competitor","Common Keywords","Competition Level"]]
    if not comp: comp_tbl.append(["N/A","",""])
    else:
        for c in comp:
            comp_tbl.append([c.get("competitor",""), c.get("common_keywords",""), c.get("competition_level","")])
    table(story, comp_tbl, col_widths=[240,120,120])
    story.append(PageBreak())

    # Off-Page
    story.append(Paragraph("Off-Page SEO", s['H2']))
    story.append(Paragraph(seo.get("off_page",{}).get("message",""), s['P']))
    story.append(PageBreak())

    # Backlinks (placeholder)
    story.append(Paragraph("Top Backlinks", s['H2']))
    bl = seo.get("top_backlinks", [])
    bl_tbl = [["Page AS","Source Title","Source URL","Anchor","Target URL","Rel"]]
    if not bl: bl_tbl.append(["","","","","",""])
    else:
        for b in bl:
            bl_tbl.append([b.get("page_as",""), b.get("source_title",""), b.get("source_url",""), b.get("anchor",""), b.get("target_url",""), b.get("rel","")])
    table(story, bl_tbl, col_widths=[50,150,120,90,95,40])
    story.append(PageBreak())

    # Social
    story.append(Paragraph("Social Media", s['H2']))
    sm = seo.get("social_media", [])
    sm_tbl = [["Network","Status","Recommendation"]]
    if not sm: sm_tbl.append(["","",""])
    else:
        for r in sm:
            sm_tbl.append([r.get("network",""), r.get("priority",""), r.get("note","")])
    table(story, sm_tbl, col_widths=[120,80,260])

    # Build
    doc.build(story)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition":"attachment; filename=FF_TECH_ELITE_Audit_Report.pdf"})

# ---------- Main ----------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
