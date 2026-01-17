
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from pathlib import Path
from typing import Dict, Any

def build_pdf(audit_id: int, url: str, overall: float, grade: str,
              category_scores: Dict[str, float], metrics: Dict[str, Any],
              out_dir: str) -> str:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pdf_path = out / f"audit_{audit_id}.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    text = c.beginText(50, 800)
    text.textLine(f"Audit Report #{audit_id}")
    text.textLine(f"URL: {url}")
    text.textLine(f"Overall: {overall:.2f} ({grade})")
    text.textLine("")
    text.textLine("Category Scores:")
    for k, v in category_scores.items():
        text.textLine(f" - {k}: {v:.2f}")
    text.textLine("")
    text.textLine("Metrics:")
    for k, v in metrics.items():
        text.textLine(f" - {k}: {v}")
    c.drawText(text)
    c.showPage()
    c.save()
    return str(pdf_path)
