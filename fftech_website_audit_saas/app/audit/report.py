
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from ..services.config import resolve_path


TITLE = 'FF Tech AI Website Audit'


def _page_header(c: canvas.Canvas, title: str):
    width, height = A4
    c.setFont('Helvetica-Bold', 16)
    c.drawString(2*cm, height - 2*cm, title)
    c.setFont('Helvetica', 10)


def render_pdf(rows: List[Dict[str, Any]], output_dir: Path, logger):
    """Legacy renderer: 1-2 pages quick summary."""
    pdf_path = resolve_path(output_dir / 'audit_summary.pdf')
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    _page_header(c, TITLE)
    y = A4[1] - 3*cm
    for i, row in enumerate(rows[:30]):
        c.drawString(2*cm, y, f"Row {i+1}: " + ', '.join(f"{k}={v}" for k,v in list(row.items())[:6]))
        y -= 0.6*cm
        if y < 2*cm:
            c.showPage(); _page_header(c, TITLE); y = A4[1] - 3*cm
    c.save()
    logger.info('PDF written: %s', pdf_path)
    return pdf_path


def render_pdf_10p(rows: List[Dict[str, Any]], output_dir: Path, logger):
    """Five-page, executive-friendly report (can be extended to 10)."""
    pdf_path = resolve_path(output_dir / 'audit_5p.pdf')
    c = canvas.Canvas(str(pdf_path), pagesize=A4)

    # Page 1: Executive summary & grading
    _page_header(c, f"{TITLE} — Executive Summary")
    c.setFont('Helvetica', 11)
    c.drawString(2*cm, A4[1] - 4*cm, 'Overall Grade: (placeholder)')
    c.drawString(2*cm, A4[1] - 5*cm, 'Summary: This is a placeholder executive summary. Replace with AI text.')
    c.showPage()

    # Page 2: Overall site health metrics
    _page_header(c, f"{TITLE} — Site Health")
    c.setFont('Helvetica', 11)
    lines = [f"{k}: {v}" for k,v in (rows[0] if rows else {}).items()][:25]
    y = A4[1] - 4*cm
    for ln in lines:
        c.drawString(2*cm, y, ln)
        y -= 0.6*cm
    c.showPage()

    # Page 3: Crawlability & Indexation (placeholder)
    _page_header(c, f"{TITLE} — Crawlability & Indexation")
    c.setFont('Helvetica', 11)
    c.drawString(2*cm, A4[1] - 4*cm, 'Placeholder crawlability metrics...')
    c.showPage()

    # Page 4: On-Page SEO & Technical (placeholder)
    _page_header(c, f"{TITLE} — On-Page & Technical")
    c.setFont('Helvetica', 11)
    c.drawString(2*cm, A4[1] - 4*cm, 'Placeholder on-page & technical metrics...')
    c.showPage()

    # Page 5: Mobile/Security/International & Conclusion
    _page_header(c, f"{TITLE} — Mobile, Security, International")
    c.setFont('Helvetica', 11)
    c.drawString(2*cm, A4[1] - 4*cm, 'Placeholder mobile/security metrics...')
    c.drawString(2*cm, 3*cm, 'Conclusion: Placeholder conclusion. Replace with AI analysis and priorities.')
    c.showPage()

    c.save()
    logger.info('5-page PDF written: %s', pdf_path)
    return pdf_path

