
# fftech_audit/ui_and_pdf.py
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from io import BytesIO
from typing import Dict, List

BRAND_PRIMARY = colors.HexColor('#6366f1')
BRAND_ACCENT = colors.HexColor('#ec4899')


def _header(c: canvas.Canvas, title: str):
    c.setFillColor(BRAND_PRIMARY)
    c.rect(0, 820, 595, 22, fill=1, stroke=0)
    c.setFont('Helvetica-Bold', 14)
    c.setFillColor(colors.white)
    c.drawString(20, 825, 'FF Tech AI • Website Audit Report')
    c.setFont('Helvetica', 11)
    c.drawRightString(575, 825, title)


def _footer(c: canvas.Canvas, text: str):
    c.setFillColor(colors.HexColor('#111827'))
    c.setFont('Helvetica', 9)
    c.drawString(20, 20, text)


def _bar_chart(c: canvas.Canvas, x: float, y: float, data: Dict[str, float]):
    max_w = 400
    c.setFont('Helvetica', 10)
    for i, (k, v) in enumerate(data.items()):
        c.setFillColor(colors.HexColor('#1e293b'))
        c.rect(x, y - i*22, max_w, 16, fill=1, stroke=0)
        c.setFillColor(BRAND_PRIMARY)
        c.rect(x, y - i*22, max_w * (v/100.0), 16, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.drawString(x + 6, y - i*22 + 12, f"{k.title()} : {v:.0f}%")


def build_pdf_report(audit, category_scores: Dict[str, float], strengths: List[str], weaknesses: List[str], priority_fixes: List[str]) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    # Page 1: Executive Summary
    _header(c, 'Executive Summary')
    c.setFillColor(colors.black)
    c.setFont('Helvetica-Bold', 18)
    c.drawString(30, 770, f"Audit for {audit.url}")
    c.setFont('Helvetica', 12)
    c.drawString(30, 745, f"Overall Score: {audit.score}%  |  Grade: {audit.grade}")
    c.setFillColor(BRAND_ACCENT)
    c.rect(30, 710, 535, 2, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont('Helvetica', 11)
    summary = (
        'Executive overview of site health across security, performance, SEO, mobile, and content. '
        'Actionable guidance follows in each section with visual breakdowns to prioritize improvements.'
    )
    c.drawString(30, 690, summary)
    c.setFont('Helvetica', 11)
    c.drawString(30, 670, 'Category Score Breakdown:')
    _bar_chart(c, 30, 650, category_scores)
    _footer(c, 'Page 1 • Executive-friendly overview')
    c.showPage()

    # Page 2: Strengths & Weaknesses
    _header(c, 'Strengths & Weaknesses')
    c.setFont('Helvetica-Bold', 14)
    c.drawString(30, 770, 'Strengths')
    c.setFont('Helvetica', 11)
    y = 750
    for s in strengths[:10]:
        c.drawString(40, y, f"• {s}")
        y -= 18
    c.setFont('Helvetica-Bold', 14)
    c.drawString(30, y-10, 'Weaknesses')
    y -= 30
    c.setFont('Helvetica', 11)
    for w in weaknesses[:10]:
        c.drawString(40, y, f"• {w}")
        y -= 18
    c.drawString(30, 100, 'Conclusion: Address top weaknesses in priority order for rapid score gains.')
    _footer(c, 'Page 2 • Highlights & risks')
    c.showPage()

    # Page 3: Priority Fixes & Roadmap
    _header(c, 'Priority Fixes & Roadmap')
    c.setFont('Helvetica-Bold', 14)
    c.drawString(30, 770, 'Priority Fixes')
    c.setFont('Helvetica', 11)
    y = 750
    for p in priority_fixes[:12]:
        c.drawString(40, y, f"• {p}")
        y -= 18
    c.setFont('Helvetica-Bold', 14)
    c.drawString(30, y-10, 'Roadmap')
    c.setFont('Helvetica', 11)
    c.drawString(40, y-30, '1) Immediate (1–2 weeks)  2) Mid-term (1–2 months)  3) Long-term (quarter)')
    c.drawString(30, 100, 'Conclusion: Sequencing fixes reduces risk and maximizes ROI.')
    _footer(c, 'Page 3 • Action plan')
    c.showPage()

    # Page 4: Technical & Performance
    _header(c, 'Technical & Performance')
    c.setFont('Helvetica', 11)
    c.drawString(30, 770, 'Summary of performance signals and caching opportunities.')
    _bar_chart(c, 30, 730, category_scores)
    c.drawString(30, 520, 'Conclusion: Improve caching, optimize images, and review third-party scripts.')
    _footer(c, 'Page 4 • Performance guidance')
    c.showPage()

    # Page 5: Certification & Branding
    _header(c, 'Certification')
    c.setFont('Helvetica-Bold', 16)
    c.drawString(30, 770, 'Certified Executive Report')
    c.setFont('Helvetica', 11)
    c.drawString(30, 745, 'Executive-ready and print-optimized with FF Tech branding.')
    c.setFillColor(BRAND_PRIMARY)
    c.rect(30, 720, 200, 120, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold', 13)
    c.drawCentredString(130, 780, 'FF Tech')
    c.setFont('Helvetica', 10)
    c.drawCentredString(130, 760, 'Website Audit SaaS')
    c.setFillColor(colors.black)
    c.setFont('Helvetica', 11)
    c.drawString(30, 580, 'Conclusion: Strengthen SEO, headers, and performance for measurable gains.')
    _footer(c, 'Page 5 • Certified & printable')
    c.showPage()

    c.save()
    return buf.getvalue()
