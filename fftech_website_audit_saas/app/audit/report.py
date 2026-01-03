
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm
from datetime import datetime


def render_pdf(path: str, brand: str, domain: str, grade: str, health_score: int, category_scores: list, exec_summary: str):
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4

    # Header
    c.setFillColor(colors.HexColor('#0B5ED7'))
    c.rect(0, height-40, width, 40, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold', 16)
    c.drawString(20, height-28, f"{brand} · Certified Website Audit")

    # Badge
    c.setFillColor(colors.black)
    c.setFont('Helvetica-Bold', 24)
    c.drawString(20, height-80, f"Grade: {grade}")
    c.setFont('Helvetica', 12)
    c.drawString(20, height-100, f"Health Score: {health_score}%")
    c.drawString(20, height-116, f"Domain: {domain}")
    c.drawString(20, height-132, f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

    # Category scores
    y = height-160
    c.setFont('Helvetica-Bold', 12)
    c.drawString(20, y, 'Category Scores:')
    y -= 14
    c.setFont('Helvetica', 11)
    for item in category_scores:
        c.drawString(30, y, f"• {item['name']}: {item['score']}%")
        y -= 12
        if y < 60:
            c.showPage()
            y = height-40

    # Executive summary
    if y < 160:
        c.showPage(); y = height-60
    c.setFont('Helvetica-Bold', 12)
    c.drawString(20, y, 'Executive Summary')
    y -= 16
    c.setFont('Helvetica', 11)
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    styles = getSampleStyleSheet()
    style = styles['BodyText']
    style.leading = 14
    # Simplified paragraph rendering
    c.drawString(20, y, exec_summary[:1000])

    # Footer certification
    c.setFont('Helvetica', 10)
    c.setFillColor(colors.HexColor('#0B5ED7'))
    c.drawString(20, 30, f"Certified by {brand} · Valid for 30 days")

    c.showPage()
    c.save()
