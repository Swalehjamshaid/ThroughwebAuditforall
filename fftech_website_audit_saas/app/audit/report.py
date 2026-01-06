from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib import colors

# Render a simple certified audit PDF

def render_pdf(path: str, brand: str, url: str, grade: str, health: int, category_scores: list, exec_summary: str) -> None:
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4

    c.setFillColor(colors.HexColor('#222222'))
    c.setFont('Helvetica-Bold', 18)
    c.drawString(2*cm, height-2.5*cm, f"{brand} — Certified Audit Report")

    c.setFillColor(colors.black)
    c.setFont('Helvetica', 12)
    c.drawString(2*cm, height-3.5*cm, f"Website: {url}")
    c.drawString(2*cm, height-4.2*cm, f"Grade: {grade}")
    c.drawString(2*cm, height-4.9*cm, f"Health Score: {health}/100")

    # Category table
    c.setFont('Helvetica-Bold', 12)
    c.drawString(2*cm, height-6*cm, 'Category Scores:')
    y = height-6.7*cm
    c.setFont('Helvetica', 11)
    for item in category_scores:
        c.drawString(2*cm, y, f"- {item['name']}: {item['score']}/100")
        y -= 0.6*cm

    # Summary paragraph
    c.setFont('Helvetica-Bold', 12)
    c.drawString(2*cm, y-0.5*cm, 'Executive Summary:')
    c.setFont('Helvetica', 11)
    textobj = c.beginText(2*cm, y-1.2*cm)
    textobj.setLeading(14)
    for line in exec_summary.split('
'):
        textobj.textLine(line.strip())
    c.drawText(textobj)

    c.showPage()
    c.save()
