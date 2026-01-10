
"""Audit report module providing PDF renderers."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm
    HAS_RL = True
except Exception:
    HAS_RL = False


def render_pdf(rows: List[Dict[str, Any]], output_dir: Path, logger) -> Optional[Path]:
    if not HAS_RL:
        logger.info('reportlab missing; render_pdf not available.')
        return None
    pdf_path = Path(output_dir).expanduser().resolve() / 'audit_rendered.pdf'
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    width, height = A4
    c.setFont('Helvetica-Bold', 14)
    c.drawString(2*cm, height-2*cm, 'Audit Report (Renderer)')
    c.setFont('Helvetica', 10)
    y = height - 3*cm
    for i, row in enumerate(rows[:40]):
        c.drawString(2*cm, y, f"Row {i+1}: " + ', '.join(f"{k}={v}" for k,v in list(row.items())[:6]))
        y -= 0.6*cm
        if y < 2*cm:
            c.showPage(); y = height - 3*cm
    c.save()
    return pdf_path


def render_pdf_10p(rows: List[Dict[str, Any]], output_dir: Path, logger) -> Optional[Path]:
    # For compatibility, call render_pdf with same semantics
    return render_pdf(rows, output_dir, logger)

