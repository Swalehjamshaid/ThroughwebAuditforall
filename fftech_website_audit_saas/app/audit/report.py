
# app/audit/report.py
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
import textwrap

def render_pdf(
    path: str,
    brand: str,
    url: str,
    grade: str,
    health_score: int,
    category_scores_list: list,
    exec_summary: str,
):
    """
    Render a one or multi-page Certified Audit PDF.

    - Title, URL, grade, health score
    - Category scores
    - Exec summary (normalized line breaks + wrapped to width)
    """
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4

    left   = 20 * mm
    line_h = 6  * mm
    y      = height - 30 * mm

    def new_page():
        nonlocal y
        c.showPage()
        y = height - 30 * mm
        c.setFont("Helvetica-Bold", 16)
        c.drawString(left, y, f"{brand} — Certified Audit")
        y -= 10 * mm
        c.setFont("Helvetica", 11)

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(left, y, f"{brand} — Certified Audit")
    y -= 10 * mm
    c.setFont("Helvetica", 11)
    c.drawString(left, y, f"URL: {url}")
    y -= line_h
    c.drawString(left, y, f"Grade: {grade}    Health: {health_score}/100")
    y -= 10 * mm

    # Category scores
    c.setFont("Helvetica-Bold", 12)
    c.drawString(left, y, "Category Scores:")
    y -= line_h
    c.setFont("Helvetica", 11)
    for item in (category_scores_list or []):
        name  = str(item.get("name", "Unknown"))
        score = str(item.get("score", "NA"))
        c.drawString(left + 5 * mm, y, f"- {name}: {score}")
        y -= line_h
        if y < 20 * mm:
            new_page()
    y -= line_h

    # Executive summary
    c.setFont("Helvetica-Bold", 12)
    c.drawString(left, y, "Executive Summary:")
    y -= line_h
    c.setFont("Helvetica", 11)

    # Normalize and wrap
    safe_summary = str(exec_summary or "")
    safe_summary = safe_summary.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs   = [p.strip() for p in safe_summary.split("\n")]
    paragraphs   = [p for p in paragraphs if p] or ["No executive summary provided."]
    max_chars    = 95  # wrap width in characters

    for para in paragraphs:
        wrapped_lines = textwrap.wrap(
            para, width=max_chars, break_long_words=True, break_on_hyphens=True
        ) or [""]
        for line in wrapped_lines:
            c.drawString(left + 5 * mm, y, line)
            y -= line_h
            if y < 20 * mm:
                new_page()
        # blank line between paragraphs
        y -= 2
        if y < 20 * mm:
            new_page()

    c.showPage()
    c.save()
