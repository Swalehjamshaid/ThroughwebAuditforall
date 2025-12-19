from fastapi import APIRouter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from io import BytesIO
from fastapi.responses import Response

router = APIRouter()

@router.get('/pdf')
def generate_pdf(site: str = 'https://example.com', grade: str = 'A'):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle("FF Tech Certified Website Audit")
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 800, "FF Tech – Certified Audit Report")
    c.setFont("Helvetica", 12)
    c.drawString(72, 770, f"Website: {site}")
    c.drawString(72, 750, f"Grade: {grade}")
    c.drawString(72, 730, "Validity: 90 days")
    c.drawString(72, 710, "This report summarizes security, SEO, performance and compliance checks.")
    c.showPage()
    c.save()
    pdf = buffer.getvalue()
    buffer.close()
    return Response(content=pdf, media_type='application/pdf')
