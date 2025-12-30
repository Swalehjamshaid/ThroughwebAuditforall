
# fftech_audit/ui_and_pdf.py
from typing import List, Dict, Any
from dataclasses import dataclass

# PDF creation
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors


@dataclass
class Row:
    label: str
    value: float


def build_rows_for_ui(metrics: Dict[str, Any]) -> List[Row]:
    """
    Map metrics to the 'Key Signals' cards expected by results.html.
    """
    def pick_float(k, default=0.0):
        v = metrics.get(k)
        try:
            return float(v)
        except Exception:
            return default

    rows = [
        Row("Performance", pick_float("signals.performance.score", 0.0)),
        Row("Mobile", pick_float("signals.mobile.score", 0.0)),
        Row("Accessibility", pick_float("signals.a11y.score", 0.0)),
        Row("Security (HTTPS)", pick_float("signals.security.https_score", 0.0)),
        Row("Indexing", pick_float("summary.category_breakdown", {}).get("Indexing", 0.0)),
        Row("Metadata", pick_float("summary.category_breakdown", {}).get("Metadata", 0.0)),
        Row("Structure", pick_float("summary.category_breakdown", {}).get("Structure", 0.0)),
    ]
    return rows


def _draw_wrapped_text(c: canvas.Canvas, text: str, x: float, y: float, max_width: float, leading=14):
    """
    Very simple text wrapper for PDF.
    """
    from reportlab.lib.utils import simpleSplit
    lines = simpleSplit(text, 'Helvetica', 11, max_width)
    for i, line in enumerate(lines):
        c.drawString(x, y - i * leading, line)
    return y - (len(lines) * leading)


def make_pdf_bytes(url: str, metrics: Dict[str, Any], rows: List[Row]) -> bytes:
    """
    Create a 5-page professional summary PDF.
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # --- Cover page ---
    c.setFillColor(colors.HexColor("#333333"))
    c.setFont("Helvetica-Bold", 22)
    c.drawString(72, h - 100, "FF Tech AI — Website Audit")
    c.setFont("Helvetica", 12)
    c.drawString(72, h - 130, f"Target: {url}")
    c.drawString(72, h - 150, f"Generated: {metrics.get('generated_at', '')} UTC")

    # Overall score & grade
    c.setFont("Helvetica-Bold", 48)
    c.setFillColor(colors.HexColor("#667eea"))
    score = metrics.get("overall.health_score", 0.0)
    c.drawString(72, h - 220, f"{score:.1f}%")

    c.setFont("Helvetica-Bold", 32)
    c.setFillColor(colors.HexColor("#00a86b"))
    c.drawString(72, h - 260, f"Grade: {metrics.get('overall.grade', '—')}")

    c.showPage()

    # --- Page 2: Executive Summary ---
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(colors.black)
    c.drawString(72, h - 80, "Executive Summary")

    y = h - 120
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, y, "Strengths")
    c.setFont("Helvetica", 11)
    y -= 20
    strengths = metrics.get("summary.strengths", [])
    if strengths:
        for s in strengths:
            y = _draw_wrapped_text(c, f"• {s}", 90, y, w - 160)
            y -= 4
    else:
        y = _draw_wrapped_text(c, "No major strengths detected.", 90, y, w - 160)

    y -= 20
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, y, "Weaknesses")
    c.setFont("Helvetica", 11)
    y -= 20
    weaknesses = metrics.get("summary.weaknesses", [])
    if weaknesses:
        for s in weaknesses:
            y = _draw_wrapped_text(c, f"• {s}", 90, y, w - 160)
            y -= 4
    else:
        y = _draw_wrapped_text(c, "No critical issues found.", 90, y, w - 160)

    y -= 20
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, y, "Priority Fixes")
    c.setFont("Helvetica", 11)
    y -= 20
    fixes = metrics.get("summary.priority_fixes", [])
    if fixes:
        for i, s in enumerate(fixes, start=1):
            y = _draw_wrapped_text(c, f"{i}. {s}", 90, y, w - 160)
            y -= 4
    else:
        y = _draw_wrapped_text(c, "Your site has strong foundations!", 90, y, w - 160)

    c.showPage()

    # --- Page 3: Category Breakdown ---
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, h - 80, "Category Breakdown")
    c.setFont("Helvetica", 12)
    y = h - 120
    cat = metrics.get("summary.category_breakdown", {})
    for k, v in cat.items():
        c.drawString(90, y, f"{k}: {v:.1f}%")
        y -= 18

    c.showPage()

    # --- Page 4: Key Signals (rows) ---
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, h - 80, "Key Signals")
    c.setFont("Helvetica", 12)
    y = h - 120
    for r in rows:
        c.drawString(90, y, f"{r.label}: {r.value:.1f}%")
        y -= 18

    c.showPage()

    # --- Page 5: All Metrics (compact) ---
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, h - 80, "All Metrics (compact)")
    c.setFont("Helvetica", 11)
    y = h - 110
    for k in sorted(metrics.keys()):
        v = metrics[k]
        line = f"{k}: {v}"
        y = _draw_wrapped_text(c, line, 72, y, w - 120, leading=13)
        y -= 4
        if y < 100:
            c.showPage()
            c.setFont("Helvetica-Bold", 18)
            c.drawString(72, h - 80, "All Metrics (cont.)")
            c.setFont("Helvetica", 11)
            y = h - 110

    c.save()
    buf.seek(0)
    return buf.read()
