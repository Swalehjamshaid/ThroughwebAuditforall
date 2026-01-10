
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional
from .external_imports import import_audit_report
from .config import resolve_path

def maybe_generate_pdf(rows: List[Dict[str, Any]], output_dir: Path, logger) -> Optional[Path]:
    audit_report, rp10, rp = import_audit_report(logger)
    if audit_report is None:
        return None
    try:
        if callable(rp10):
            logger.info('Generating PDF via render_pdf_10p...')
            pdf_path = rp10(rows, output_dir=output_dir, logger=logger)  # type: ignore
            return resolve_path(pdf_path) if pdf_path else None
        elif callable(rp):
            logger.info('Generating PDF via render_pdf...')
            pdf_path = rp(rows, output_dir=output_dir, logger=logger)  # type: ignore
            return resolve_path(pdf_path) if pdf_path else None
        else:
            logger.info('No PDF renderers available in app.audit.report.')
            return None
    except Exception as e:
        logger.error('PDF generation failed: %s', e, exc_info=True)
        return None

def fallback_pdf(rows: List[Dict[str, Any]], graphs: List[Path], output_dir: Path, logger) -> Optional[Path]:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import cm
    except Exception:
        logger.info('reportlab not installed; skipping fallback PDF.')
        return None
    pdf_path = resolve_path(output_dir/'report.pdf')
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    width, height = A4
    c.setFont('Helvetica-Bold', 14)
    c.drawString(2*cm, height-2*cm, 'Audit Report')
    c.setFont('Helvetica', 10)
    y = height - 3*cm
    for i, row in enumerate(rows[:30]):
        c.drawString(2*cm, y, f"Row {i+1}: " + ', '.join(f"{k}={v}" for k,v in list(row.items())[:6]))
        y -= 0.6*cm
        if y < 2*cm:
            c.showPage(); y = height - 2*cm
    for g in graphs[:6]:
        c.showPage(); c.drawImage(str(g), 2*cm, 4*cm, width=width-4*cm, height=height-8*cm, preserveAspectRatio=True, mask='auto')
        c.setFont('Helvetica', 10); c.drawString(2*cm, 2.5*cm, f'Figure: {g.name}')
    c.save(); logger.info('Fallback PDF created at: %s', pdf_path)
    return pdf_path
