from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import io, matplotlib.pyplot as plt

def generate_professional_pdf(audit_data, url, score, grade):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = []

    # --- PAGE 1: BRANDED COVER ---
    story.append(Paragraph(f"FF TECH CERTIFIED AUDIT", styles['Title']))
    story.append(Spacer(1, 40))
    story.append(Paragraph(f"<b>TARGET URL:</b> {url}", styles['Heading2']))
    story.append(Paragraph(f"<b>OVERALL SCORE:</b> {score}%", styles['Heading2']))
    story.append(Paragraph(f"<b>GRADE:</b> {grade}", styles['Heading2']))
    story.append(Spacer(1, 200))
    story.append(Paragraph("This report is a confidential AI-generated technical roadmap.", styles['Normal']))
    story.append(PageBreak())

    # --- PAGE 2: GRAPHICAL PRESENTATION ---
    plt.figure(figsize=(8, 5))
    names = list(audit_data.keys())
    values = [v['score'] for v in audit_data.values()]
    plt.barh(names, values, color=['#10B981', '#3B82F6', '#6366F1', '#F59E0B', '#EF4444'])
    plt.title("Category Score Distribution")
    
    img_buf = io.BytesIO()
    plt.savefig(img_buf, format='png', bbox_inches='tight')
    story.append(Paragraph("Graphical Metric Overview", styles['Heading2']))
    story.append(Image(img_buf, width=500, height=300))
    story.append(PageBreak())

    # --- PAGE 3-5: DETAILED CATEGORY BREAKDOWNS ---
    for i in range(3, 6):
        story.append(Paragraph(f"Technical Analysis: Page {i}", styles['Heading2']))
        story.append(Spacer(1, 10))
        # Logic to iterate through specific metric clusters
        story.append(Paragraph("Detailed findings for metrics in this category group...", styles['Normal']))
        story.append(PageBreak())

    doc.build(story)
    return buffer.getvalue()
