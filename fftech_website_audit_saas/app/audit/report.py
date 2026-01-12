# app/audit/report.py
"""
Professional PDF Website Audit Report Generator
Enhanced version - January 2026

Features:
- Color-coded score indicators (green/yellow/red)
- Visual progress bars for categories
- Prominent grade badge
- Clean section layout with proper spacing
- Confidential watermark
- Page numbering + generation info
- Optional recommendations section
- Backward compatible with original signature
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Flowable,
)


def get_score_color(score: int) -> colors.Color:
    """Return traffic-light style color based on score"""
    if score >= 85:
        return colors.green
    if score >= 70:
        return colors.Color(1, 0.6, 0)  # orange
    return colors.red


def create_score_bar(score: int, width_mm: float = 60) -> Flowable:
    """Create a simple horizontal progress bar for score visualization"""
    filled_width = width_mm * (score / 100)
    empty_width = width_mm - filled_width

    bar = Table(
        [["" for _ in range(2)]],
        colWidths=[filled_width * mm, empty_width * mm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), get_score_color(score)),
            ("BACKGROUND", (1, 0), (1, -1), colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ])
    )
    return bar


def render_pdf(
    output_path: str | Path,
    brand_name: str,
    audited_url: str,
    grade: str,
    health_score: int,
    category_scores: List[Dict[str, Any]],
    executive_summary: str = "",
    recommendations: str | None = None,
    audit_date: datetime | None = None,
    logo_path: str | Path | None = None,  # Ready for future logo support
):
    """
    Generate a professional, multi-page website audit report PDF
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if audit_date is None:
        audit_date = datetime.utcnow()

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=30 * mm,
        bottomMargin=25 * mm,
    )

    styles = getSampleStyleSheet()

    # ── Custom Styles ───────────────────────────────────────────────────────────
    title_style = ParagraphStyle(
        name="Title",
        parent=styles["Heading1"],
        fontSize=24,
        spaceAfter=8,
        alignment=TA_CENTER,
        textColor=colors.darkblue,
    )

    subtitle_style = ParagraphStyle(
        name="Subtitle",
        parent=styles["Normal"],
        fontSize=12,
        alignment=TA_CENTER,
        textColor=colors.darkslategray,
        spaceAfter=16,
    )

    section_header = ParagraphStyle(
        name="SectionHeader",
        parent=styles["Heading2"],
        fontSize=16,
        spaceBefore=24,
        spaceAfter=12,
        textColor=colors.darkblue,
    )

    normal = ParagraphStyle(
        name="Normal",
        parent=styles["Normal"],
        fontSize=11,
        leading=14,
        spaceAfter=10,
    )

    # ── Content Flow ────────────────────────────────────────────────────────────
    elements = []

    # Header Block
    elements.extend([
        Paragraph(f"{brand_name} • Certified Website Audit Report", title_style),
        Spacer(1, 4 * mm),
        Paragraph(f"Audited URL: {audited_url}", subtitle_style),
        Paragraph(
            f"Audit Date: {audit_date.strftime('%B %d, %Y')}  •  "
            f"Overall Score: {health_score}/100  •  Grade: {grade}",
            normal
        ),
        Spacer(1, 18 * mm),
    ])

    # Overall Grade Badge
    grade_color = get_score_color(health_score)
    badge = Table(
        [[f"Overall Grade: {grade}", f"{health_score}/100"]],
        colWidths=[110 * mm, 60 * mm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), grade_color),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
            ("BACKGROUND", (1, 0), (1, -1), colors.lightgrey),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 14),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 1, colors.white),
        ])
    )
    elements.extend([badge, Spacer(1, 20 * mm)])

    # Category Scores Section
    elements.append(Paragraph("Category Performance", section_header))

    table_data = [["Category", "Score", "Visual"]]
    for item in category_scores or []:
        name = str(item.get("name", "Unknown")).replace("_", " ").title()
        score = int(item.get("score", 0))
        table_data.append([
            name,
            str(score),
            create_score_bar(score)
        ])

    category_table = Table(
        table_data,
        colWidths=[doc.width * 0.45, doc.width * 0.15, doc.width * 0.40],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightblue),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.darkblue),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("ALIGN", (2, 0), (2, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 12),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])
    )
    elements.extend([category_table, Spacer(1, 20 * mm)])

    # Executive Summary
    elements.append(Paragraph("Executive Summary", section_header))

    summary_text = (executive_summary or "No executive summary available.").strip()
    for para in summary_text.split("\n\n"):
        cleaned = para.strip()
        if cleaned:
            elements.append(Paragraph(cleaned, normal))

    # Recommendations (optional)
    if recommendations:
        elements.append(Spacer(1, 24 * mm))
        elements.append(Paragraph("Key Recommendations", section_header))
        for rec in recommendations.split("\n\n"):
            cleaned = rec.strip()
            if cleaned:
                elements.append(Paragraph(f"• {cleaned}", normal))

    # ── Page Template with Watermark & Footer ──────────────────────────────────
    def on_page(canvas, doc):
        page_num = canvas.getPageNumber()

        canvas.saveState()
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.grey)

        # Footer - right aligned
        canvas.drawRightString(
            doc.width + doc.rightMargin,
            12 * mm,
            f"Page {page_num} • Confidential • Generated {datetime.utcnow():%Y-%m-%d}"
        )

        # Diagonal CONFIDENTIAL watermark
        canvas.setFont("Helvetica-Bold", 52)
        canvas.setFillColorRGB(0.92, 0.92, 0.92)
        canvas.rotate(45)
        canvas.drawString(160 * mm, -160 * mm, "CONFIDENTIAL")
        canvas.restoreState()

    doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)


# ── Backward compatibility with your original function signature ─────────────
def render_pdf_legacy(
    path: str,
    brand: str,
    url: str,
    grade: str,
    health_score: int,
    category_scores_list: list,
    exec_summary: str,
) -> None:
    """Maintain compatibility with existing code calls"""
    render_pdf(
        output_path=path,
        brand_name=brand,
        audited_url=url,
        grade=grade,
        health_score=health_score,
        category_scores=category_scores_list,
        executive_summary=exec_summary,
    )
