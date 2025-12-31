
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from datetime import datetime

def _brand(c):
    c.setFont("Helvetica-Bold", 22)
    c.drawString(2*cm, 27*cm, "FF Tech – Certified Website Audit")
    c.setFont("Helvetica", 12)
    c.drawString(2*cm, 26.2*cm, "World-class audit aligned to global standards")

def generate_report(site: str, grade: str, summary: str, metrics: dict, accumulated: bool=False) -> bytes:
    from io import BytesIO
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _brand(c)
    c.setFont("Helvetica", 12)
    c.drawString(2*cm, 25*cm, f"Website: {site}")
    c.drawString(2*cm, 24.3*cm, f"Grade: {grade}")
    c.drawString(2*cm, 23.6*cm, f"Type: {'Accumulated' if accumulated else 'Daily'} Report")
    c.drawString(2*cm, 22.9*cm, f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    c.drawString(2*cm, 22.2*cm, "Validity: 30 days")
    text = c.beginText(2*cm, 21*cm)
    text.setFont("Helvetica", 11)
    text.textLines(summary)
    c.drawText(text)
    y = 18*cm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2*cm, y, "Key Metrics:")
    c.setFont("Helvetica", 11)
    y -= 0.7*cm
    for k, v in list(metrics.items())[:12]:
        c.drawString(2*cm, y, f"- {k}: {v}")
        y -= 0.6*cm
        if y < 3*cm:
            c.showPage(); _brand(c); y = 25*cm
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(2*cm, 2*cm, "Certification: FF Tech Quality Assurance • Based on Lighthouse, CWV, WCAG 2.2, OWASP ASVS")
    c.showPage(); c.save()
    return buf.getvalue()
