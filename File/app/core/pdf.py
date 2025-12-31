
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib import colors

TITLE = "FF Tech AI Website Audit — Certified Report"

sections = [
    "Executive Summary & Overall Grade",
    "Crawlability & Indexation",
    "On-Page SEO",
    "Performance & Technical",
    "Mobile, Security & International + Opportunities"
]

def build_pdf(buf, audit_id: str):
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    for i, section in enumerate(sections, start=1):
        c.setFont("Helvetica-Bold", 16)
        c.drawString(2*cm, height-2*cm, TITLE)
        c.setFont("Helvetica", 11)
        c.drawString(2*cm, height-3*cm, f"Audit ID: {audit_id}")
        c.drawString(2*cm, height-3.7*cm, f"Page {i}: {section}")
        y = height-6*cm
        for label, val in [("Health", 78), ("Crawl", 72), ("SEO", 69), ("Perf", 75), ("Mobile/Sec", 70)]:
            c.setFillColor(colors.lightgrey)
            c.rect(2*cm, y, 12*cm, 0.6*cm, fill=1, stroke=0)
            c.setFillColor(colors.darkblue)
            c.rect(2*cm, y, 12*cm*val/100.0, 0.6*cm, fill=1, stroke=0)
            c.setFillColor(colors.black)
            c.drawString(2*cm, y+0.8*cm, f"{label}: {val}%")
            y -= 1.6*cm
        c.setFont("Helvetica-Oblique", 10)
        c.drawString(2*cm, 2*cm, "Conclusion: Placeholder conclusions per section. Replace with real insights.")
        c.showPage()
    c.save()
