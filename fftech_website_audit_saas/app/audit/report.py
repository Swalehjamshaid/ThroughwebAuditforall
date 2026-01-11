from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm


def render_pdf(path: str, brand: str, url: str, grade: str, health_score: int, category_scores_list: list, exec_summary: str):
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    y = height - 30*mm

    c.setFont('Helvetica-Bold', 16)
    c.drawString(20*mm, y, f'{brand} — Certified Audit')
    y -= 10*mm
    c.setFont('Helvetica', 11)
    c.drawString(20*mm, y, f'URL: {url}')
    y -= 6*mm
    c.drawString(20*mm, y, f'Grade: {grade}    Health: {health_score}/100')
    y -= 10*mm

    c.setFont('Helvetica-Bold', 12)
    c.drawString(20*mm, y, 'Category Scores:')
    y -= 6*mm
    c.setFont('Helvetica', 11)
    for item in (category_scores_list or []):
        c.drawString(25*mm, y, f"- {item.get('name')}: {item.get('score')}")
        y -= 6*mm
    y -= 6*mm

    c.setFont('Helvetica-Bold', 12)
    c.drawString(20*mm, y, 'Executive Summary:')
    y -= 6*mm
    c.setFont('Helvetica', 11)
    for line in (exec_summary or '').split('
'):
        c.drawString(25*mm, y, line[:100])
        y -= 6*mm

    c.showPage()
    c.save()
