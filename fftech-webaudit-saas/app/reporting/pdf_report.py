from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from datetime import datetime

def generate_pdf(path: str, site_url: str, grade: str, score: float, summary: dict):
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4

    # Header branding
    c.setFillColor(colors.HexColor('#0F172A'))
    c.rect(0, height-60, width, 60, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(20*mm, height-40, "FF Tech – Certified Website Audit Report")

    # Certification stamp (simple label)
    c.setFillColor(colors.HexColor('#22C55E'))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(width-70*mm, height-35, "CERTIFIED")

    # Info block
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 12)
    c.drawString(20*mm, height-80, f"Website: {site_url}")
    c.drawString(20*mm, height-95, f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

    # Grade & score
    c.setFont("Helvetica-Bold", 26)
    c.setFillColor(colors.HexColor('#334155'))
    c.drawString(20*mm, height-120, f"Grade: {grade}")
    c.setFont("Helvetica-Bold", 20)
    c.drawString(90*mm, height-120, f"Score: {score:.1f}")

    # Summary table
    y = height - 150
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20*mm, y, "Summary of Findings")
    y -= 10
    c.line(20*mm, y, width-20*mm, y)
    y -= 10
    c.setFont("Helvetica", 11)
    for k, v in list(summary.items())[:20]:
        c.drawString(20*mm, y, f"- {k}: {v}")
        y -= 12
        if y < 40*mm:
            c.showPage()
            y = height - 40
    c.showPage()
    c.save()
