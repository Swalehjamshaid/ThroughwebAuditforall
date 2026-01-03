
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from datetime import datetime
import os

REPORT_DIR = os.path.join(os.getcwd(), 'reports')
os.makedirs(REPORT_DIR, exist_ok=True)


def grade_from_score(score: float) -> str:
    if score >= 90: return 'A+'
    if score >= 80: return 'A'
    if score >= 70: return 'B'
    if score >= 60: return 'C'
    if score >= 50: return 'D'
    return 'E'


def render_pdf(audit, metrics: dict, website_url: str) -> str:
    filename = f"audit_{audit.id}.pdf"
    path = os.path.join(REPORT_DIR, filename)
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4

    logo_path = os.path.join(os.getcwd(), 'assets', 'logo_fftech.png')
    if os.path.exists(logo_path):
        c.drawImage(ImageReader(logo_path), 40, height - 140, width=200, height=100, mask='auto')

    c.setFont('Helvetica-Bold', 16)
    c.drawString(260, height - 80, 'FF Tech — Certified Website Audit')

    c.setFont('Helvetica', 12)
    c.drawString(40, height - 160, f"Website: {website_url}")
    c.drawString(40, height - 180, f"Audit ID: {audit.id}")
    c.drawString(40, height - 200, f"Date: {datetime.utcnow().isoformat()}Z")

    score = audit.health_score or 0
    grade = grade_from_score(score)
    c.setFont('Helvetica-Bold', 14)
    c.drawString(40, height - 230, f"Overall Score: {score:.1f} / 100  |  Grade: {grade}")

    c.setFont('Helvetica', 12)
    y = height - 260
    c.drawString(40, y, 'Key Findings:')
    y -= 20
    for k, v in list(metrics.items())[:30]:
        c.drawString(60, y, f"- {k}: {v}")
        y -= 18
        if y < 80:
            c.showPage()
            y = height - 60

    c.showPage()
    c.save()
    return path
