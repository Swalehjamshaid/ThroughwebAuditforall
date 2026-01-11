import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from datetime import datetime

from .grader import compute_metrics
from .audit import get_items_for_audit, get_audit_by_id

def generate_pdf_report(conn, audit_id, chart_paths):
    audit = get_audit_by_id(conn, audit_id)
    items = get_items_for_audit(conn, audit_id)
    metrics = compute_metrics(conn, audit_id)

    out_dir = 'reports'
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, f'audit_{audit_id}_report.pdf')

    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    c.setFillColor(colors.HexColor('#022b3a'))
    c.setFont('Helvetica-Bold', 16)
    c.drawString(2*cm, height - 2*cm, f"Audit Report: {audit['title']}")
    c.setFont('Helvetica', 10)
    c.setFillColor(colors.black)
    c.drawString(2*cm, height - 2.7*cm, f"Category: {audit['category']}  |  Date: {audit['date']}  |  Generated: {datetime.utcnow().isoformat()}")

    data = [
        ['Total Items', metrics['total_items']],
        ['Completed Items', metrics['completed_items']],
        ['Avg Score', metrics['avg_score']],
        ['Weighted Score', metrics['weighted_score']],
        ['Compliance Rate (%)', metrics['compliance_rate']],
    ]
    table = Table(data, colWidths=[6*cm, 4*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#bfd7ea')),
        ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('FONT', (0,0), (-1,-1), 'Helvetica'),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
    ]))
    table.wrapOn(c, width, height)
    table.drawOn(c, 2*cm, height - 8*cm)

    y = height - 14*cm
    for key in ['bar', 'pie', 'line']:
        filename = chart_paths.get(key)
        if filename:
            img_path = os.path.join('static', 'img', filename)
            if os.path.exists(img_path):
                c.drawImage(img_path, 2*cm, y, width=16*cm, height=6*cm, preserveAspectRatio=True)
                y -= 7*cm

    data2 = [['Item', 'Score', 'Weight', 'Status']] + [[it['item'], it['score'], it['weight'], it['status']] for it in items[:20]]
    table2 = Table(data2, colWidths=[8*cm, 2.5*cm, 2.5*cm, 3*cm])
    table2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e1e5f2')),
        ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
        ('ALIGN', (1,1), (-1,-1), 'CENTER'),
        ('FONT', (0,0), (-1,-1), 'Helvetica')
    ]))
    table2.wrapOn(c, width, height)
    table2.drawOn(c, 2*cm, max(3*cm, y))

    c.showPage()
    c.save()
    return pdf_path
