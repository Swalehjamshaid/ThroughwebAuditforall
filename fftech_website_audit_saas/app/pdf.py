import os
from typing import Optional
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

def render_certified_pdf(path: str, url: str, grade: str, score: int, date: str, logo_path: Optional[str] = None):
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    if logo_path and os.path.exists(logo_path):
        c.drawImage(logo_path, 40, height-120, width=140, height=80, preserveAspectRatio=True, mask='auto')
    c.setFont("Helvetica-Bold", 18)
    c.drawString(200, height-80, "FF Tech – Certified Website Audit")
    c.setFont("Helvetica", 12)
    c.drawString(40, height-150, f"Website: {url}")
    c.drawString(40, height-170, f"Date: {date}")
    c.drawString(40, height-190, f"Grade: {grade}")
    c.drawString(40, height-210, f"Score: {score}/100")
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(40, height-230, "Certification valid for 30 days from audit date.")
    c.showPage(); c.save()
