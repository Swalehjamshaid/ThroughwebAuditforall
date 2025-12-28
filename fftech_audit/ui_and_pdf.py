
# ui_and_pdf.py
"""
5-page PDF generator (ReportLab)
- Charts: vector bars & progress (no matplotlib)
- Pages: Exec Summary, Category Performance, Crawlability/SEO, Performance/Security, Priorities/ROI
"""

import io, re, datetime
from typing import Dict, Any, List
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

FF_TECH_LOGO_TEXT = "FF TECH AI • Website Audit"
FF_TECH_BRAND = "FF Tech"

def draw_bar_chart(c, x, y, w, h, labels: List[str], values: List[float], max_val=100):
    n = len(values)
    if n == 0: return
    bar_w = w / (n*1.6)
    gap = bar_w * 0.6
    c.setFont("Helvetica", 8)
    for i, (lab, val) in enumerate(zip(labels, values)):
        bx = x + i*(bar_w+gap)
        bh = (val/max_val) * (h-16)
        c.setFillColor(colors.HexColor("#2E86C1"))
        c.rect(bx, y, bar_w, bh, fill=1, stroke=0)
        c.setFillColor(colors.black)
        c.drawString(bx, y-12, lab[:12])

def draw_progress_bar(c, x, y, w, h, val, color="#16a34a"):
    c.setStrokeColor(colors.HexColor("#334155")); c.setFillColor(colors.HexColor("#334155"))
    c.rect(x, y, w, h, fill=1, stroke=0)
    c.setFillColor(colors.HexColor(color))
    pw = max(0, min(w, (val/100.0)*w))
    c.rect(x, y, pw, h, fill=1, stroke=0)

def build_pdf_report(audit_obj, metrics: Dict[int, Dict[str, Any]]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    # Page 1 - Cover & Executive Summary
    c.setFillColor(colors.HexColor("#0A2540")); c.rect(0, H-2.8*cm, W, 2.8*cm, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 18); c.drawString(2*cm, H-1.7*cm, FF_TECH_LOGO_TEXT)
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 16); c.drawString(2*cm, H-4.2*cm, "Executive Summary")
    summary = metrics[3]["value"]
    txt = c.beginText(2*cm, H-5.2*cm); txt.setFont("Helvetica", 11)
    for line in re.findall(".{1,95}(?:\\s|$)", summary): txt.textLine(line.strip())
    c.drawText(txt)
    c.setFont("Helvetica-Bold", 14); c.drawString(2*cm, H-12*cm, "Site Health:")
    c.setFont("Helvetica", 12); c.drawString(6*cm, H-12*cm, f"{metrics[1]['value']}%  Grade: {metrics[2]['value']}")
    draw_progress_bar(c, 2*cm, H-13.2*cm, 16*cm, 0.6*cm, metrics[1]["value"])
    sev = metrics[7]["value"]
    c.setFont("Helvetica", 12); c.drawString(2*cm, H-14.5*cm, f"Errors: {sev['errors']}  Warnings: {sev['warnings']}  Notices: {sev['notices']}")
    c.setFont("Helvetica-Oblique", 10); c.drawString(2*cm, 1.5*cm, f"{FF_TECH_BRAND} • Certified Report • Generated: {datetime.datetime.utcnow().isoformat()}")
    c.showPage()

    # Page 2 - Category Performance Chart
    c.setFont("Helvetica-Bold", 16); c.drawString(2*cm, H-2.8*cm, "Category Performance")
    cats = metrics[8]["value"]; labs = list(cats.keys()); vals = [cats[k] for k in labs]
    draw_bar_chart(c, 2*cm, H-13*cm, 16*cm, 9*cm, labs, vals, 100)
    c.setFont("Helvetica", 11); y = H-13.5*cm
    for k, v in cats.items(): c.drawString(2*cm, y, f"{k}: {int(v)}"); y -= 0.6*cm
    c.setFont("Helvetica-Oblique", 10); c.drawString(2*cm, 1.5*cm, "Conclusion: Improve security headers & fix broken links; then optimize performance.")
    c.showPage()

    # Page 3 - Crawlability & On-Page SEO
    c.setFont("Helvetica-Bold", 16); c.drawString(2*cm, H-2.8*cm, "Crawlability & On-Page SEO")
    c.setFont("Helvetica", 11)
    items = [
        f"Broken internal links: {metrics[27]['value']}",
        f"Broken external links: {metrics[28]['value']}",
        f"Canonical present: {'No' if metrics[32]['value'] else 'Yes'}",
        f"Missing meta description: {'Yes' if metrics[45]['value'] else 'No'}",
        f"Open Graph/Twitter: {'Present' if metrics[62]['value']==0 else 'Missing'}",
    ]
    y = H-4.5*cm
    for t in items: c.drawString(2*cm, y, t); y -= 0.8*cm
    c.setFont("Helvetica-Oblique", 10); c.drawString(2*cm, 1.5*cm, "Conclusion: Fix metadata gaps and link integrity to improve discovery & rich snippets.")
    c.showPage()

    # Page 4 - Performance & Security
    c.setFont("Helvetica-Bold", 16); c.drawString(2*cm, H-2.8*cm, "Performance & Security")
    c.setFont("Helvetica", 11)
    perf_items = [
        f"Page size (KB): {metrics[84]['value']}",
        f"Response time (ms): {metrics[91]['value']}",
        f"Render-blocking (approx): {metrics[88]['value']}",
        f"Compression enabled: {'Yes' if metrics[95]['value'] else 'No'}",
        f"Missing security headers: {metrics[110]['value']}",
        f"HTTPS: {'Yes' if metrics[105]['value'] else 'No'}",
    ]
    y = H-4.5*cm
    for t in perf_items: c.drawString(2*cm, y, t); y -= 0.8*cm
    draw_progress_bar(c, 2*cm, H-12.5*cm, 8*cm, 0.6*cm, min(100, max(0, 100 - metrics[110]['value']*10)), "#ef4444")
    c.setFont("Helvetica-Oblique", 10); c.drawString(2*cm, 1.5*cm, "Conclusion: Enable caching/compression, reduce blocking resources, enforce modern security headers.")
    c.showPage()

    # Page 5 - Priorities & ROI
    c.setFont("Helvetica-Bold", 16); c.drawString(2*cm, H-2.8*cm, "Priorities, Opportunities & ROI")
    c.setFont("Helvetica", 11)
    y = H-4.5*cm
    c.drawString(2*cm, y, "Priority Fixes:"); y -= 0.8*cm
    for p in metrics[6]["value"]: c.drawString(3*cm, y, f"- {p}"); y -= 0.7*cm
    y -= 0.3*cm
    c.drawString(2*cm, y, f"Quick Wins Score: {metrics[182]['value']}"); y -= 0.7*cm
    c.drawString(2*cm, y, f"Speed Improvement Potential: {metrics[189]['value']}"); y -= 0.7*cm
    c.drawString(2*cm, y, f"Security Improvement Potential: {metrics[191]['value']}"); y -= 0.7*cm
    c.drawString(2*cm, y, f"Overall Growth Readiness: {metrics[200]['value']}")
    c.setFont("Helvetica-Oblique", 10); c.drawString(2*cm, 1.5*cm, "Conclusion: Priority execution delivers near-term ROI and strengthens long-term stability.")
    c.showPage(); c.save()
    pdf = buf.getvalue(); buf.close()
    return pdf
