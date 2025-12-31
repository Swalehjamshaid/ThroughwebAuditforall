
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib import colors

def build_pdf(buf, audit_id: str):
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2*cm, height-2*cm, "FF Tech AI Website Audit — Certified Report")
    c.setFont("Helvetica", 11)
    c.drawString(2*cm, height-3*cm, f"Audit ID: {audit_id}")
    y = height-4*cm
    for section in [
        "Executive Summary & Overall Grade",
        "Crawlability & Indexation",
        "On-Page SEO",
        "Performance & Technical",
        "Mobile, Security & International + Opportunities"
    ]:
        c.drawString(2*cm, y, f"Section: {section}")
        y -= 1.2*cm
    c.showPage()
    c.save()
