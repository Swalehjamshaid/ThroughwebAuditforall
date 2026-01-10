
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional

# These functions are called by pdf_service.maybe_generate_pdf if present

def render_pdf_10p(rows: List[Dict[str, Any]], output_dir: Path, logger) -> Optional[Path]:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import inch
    except Exception:
        logger.info('reportlab not installed; render_pdf_10p unavailable.')
        return None
    pdf_path = Path(output_dir) / 'report_10p.pdf'
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    width, height = letter
    c.setFont('Helvetica-Bold', 16)
    c.drawString(1*inch, height-1*inch, 'Audit Report (10p)')
    c.setFont('Helvetica', 10)
    y = height - 1.5*inch
    for i, row in enumerate(rows[:10]):
        c.drawString(1*inch, y, f"Row {i+1}: " + ', '.join(f"{k}={v}" for k,v in list(row.items())[:6]))
        y -= 0.4*inch
        if y < 1*inch:
            c.showPage(); y = height - 1.5*inch
    c.save()
    logger.info('render_pdf_10p wrote: %s', pdf_path)
    return pdf_path


def render_pdf(rows: List[Dict[str, Any]], output_dir: Path, logger) -> Optional[Path]:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import inch
    except Exception:
        logger.info('reportlab not installed; render_pdf unavailable.')
        return None
    pdf_path = Path(output_dir) / 'report_simple.pdf'
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    width, height = letter
    c.setFont('Helvetica-Bold', 16)
    c.drawString(1*inch, height-1*inch, 'Audit Report')
    c.setFont('Helvetica', 10)
    y = height - 1.5*inch
    for i, row in enumerate(rows[:25]):
        c.drawString(1*inch, y, f"Row {i+1}: " + ', '.join(f"{k}={v}" for k,v in list(row.items())[:6]))
        y -= 0.4*inch
        if y < 1*inch:
            c.showPage(); y = height - 1.5*inch
    c.save()
    logger.info('render_pdf wrote: %s', pdf_path)
    return pdf_path
