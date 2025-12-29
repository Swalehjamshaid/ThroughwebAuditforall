
# fftech_audit/ui_and_pdf.py
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO

def build_pdf_report(audit, category_scores, strengths, weaknesses, priority_fixes) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica", 12)
    c.drawString(50, 800, "FF Tech AI • Audit Report")
    c.drawString(50, 780, f"URL: {getattr(audit, 'url', '')}")
    c.drawString(50, 760, f"Score: {getattr(audit, 'score', '')} Grade: {getattr(audit, 'grade', '')}")
    c.drawString(50, 740, "This is a simple placeholder PDF. (You can replace it with your full design.)")
    c.showPage()
    c.save()
    data = buf.getvalue()
    buf.close()
    return data
