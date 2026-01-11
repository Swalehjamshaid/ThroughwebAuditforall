
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

    - Writes title, URL, grade, health score
    - Prints category scores
    - Wraps and prints exec_summary safely (normalizes line breaks, wraps long lines)
    """
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4

    # Margins & vertical cursor
    left = 20 * mm
    line_h = 6 * mm
    y = height - 30 * mm

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

    # URL, grade, score
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
        name = str(item.get("name", "Unknown"))
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

    # Normalize line breaks and wrap text
    safe_summary = str(exec_summary or "")
    safe_summary = safe_summary.replace("\r\n", "\n").replace("\r", "\n")

    # Break into paragraphs by newline first
    paragraphs = [p.strip() for p in safe_summary.split("\n")]
    paragraphs = [p for p in paragraphs if p] or ["No executive summary provided."]

    # Wrap lines to a reasonable width (characters); adjust as needed
    max_chars = 95

    for para in paragraphs:
        wrapped_lines = textwrap.wrap(para, width=max_chars, break_long_words=True, break_on_hyphens=True)
        if not wrapped_lines:
            wrapped_lines = [""]

        for line in wrapped_lines:
            c.drawString(left + 5 * mm, y, line)
            y -= line_h
            if y < 20 * mm:
                new_page()

        # Blank line between paragraphs
        y -= 2
        if y < 20 * mm:
            new_page()

    # Finalize
    c.showPage()
    c.save()
