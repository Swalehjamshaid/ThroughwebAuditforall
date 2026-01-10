"""FFTech Website Audit SaaS - Professional PDF Report Generator

Modern implementation using ReportLab flowables with:
- Clean sectioning
- Summary statistics
- Key findings table
- Optional bilingual support (English primary)
- Better error handling
- Date-based filename
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        PageBreak,
    )
    HAS_RL = True
except ImportError:
    HAS_RL = False


def render_pdf(
    rows: List[Dict[str, Any]],
    output_dir: Path,
    logger,
    *,
    brand_name: str = "FFTech Audit",
    audit_date: Optional[str | datetime.date] = None,
    overall_score: Optional[float] = None,     # 0-100
    overall_grade: Optional[str] = None,       # A+/A/B/C etc
    website_url: Optional[str] = None,
    version: str = "1.0",
) -> Optional[Path]:
    """
    Generate professional PDF audit report

    Args:
        rows: List of audit findings (each dict should contain at least:
              'category', 'issue', 'severity', 'description', 'recommendation', 'impact')
        output_dir: Where to save the PDF
        logger: Application logger
        brand_name: Company/brand name for header
        audit_date: Date of audit (defaults to today)
        overall_score: Optional total score 0-100
        overall_grade: Optional letter grade
        website_url: Optional audited website address
        version: Report version

    Returns:
        Path to generated PDF or None if generation failed / reportlab missing
    """
    if not HAS_RL:
        logger.warning("reportlab package not installed - PDF generation skipped")
        return None

    # Prepare output filename
    today = datetime.date.today().isoformat()
    safe_name = f"fftech-audit-{today}.pdf"
    pdf_path = output_dir.expanduser().resolve() / safe_name

    logger.info(f"Starting PDF report generation → {pdf_path}")

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=2.2*cm,
        leftMargin=2.2*cm,
        topMargin=2.5*cm,
        bottomMargin=2.5*cm
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        textColor=colors.darkblue,
        spaceAfter=18
    )

    section_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        textColor=colors.navy,
        spaceBefore=18,
        spaceAfter=10
    )

    normal_style = ParagraphStyle(
        'Normal',
        parent=styles['Normal'],
        fontSize=10,
        leading=13
    )

    small_style = ParagraphStyle(
        'Small',
        parent=styles['Normal'],
        fontSize=9,
        leading=11,
        textColor=colors.grey
    )

    elements = []

    # ── Header ────────────────────────────────────────────────────────────────
    elements.append(Paragraph(f"{brand_name} - Website Audit Report", title_style))

    if website_url:
        elements.append(Paragraph(f"Website: {website_url}", normal_style))

    current_date = (
        audit_date.strftime("%B %d, %Y")
        if isinstance(audit_date, datetime.date)
        else (audit_date or today)
    )

    header_info = f"Report Date: {current_date}  •  Version: {version}"
    elements.append(Paragraph(header_info, small_style))

    if overall_score is not None:
        grade_text = f"Overall Grade: {overall_grade} " if overall_grade else ""
        score_text = f"({overall_score:.1f}/100)"
        elements.append(Paragraph(grade_text + score_text, normal_style))

    elements.append(Spacer(1, 1.4*cm))

    # ── Executive Summary ─────────────────────────────────────────────────────
    elements.append(Paragraph("Executive Summary", section_style))

    total_issues = len(rows)
    critical = sum(1 for r in rows if r.get('severity', '').lower() == 'critical')
    high = sum(1 for r in rows if r.get('severity', '').lower() == 'high')

    summary_text = (
        f"This report contains a comprehensive audit of the website. "
        f"Total issues found: <b>{total_issues}</b>. "
        f"Among them: <font color='red'><b>{critical}</b></font> critical "
        f"and <font color='orange'><b>{high}</b></font> high severity issues "
        f"that should be addressed as a priority."
    )
    elements.append(Paragraph(summary_text, normal_style))
    elements.append(Spacer(1, 1*cm))

    # ── Key Findings Table ────────────────────────────────────────────────────
    if rows:
        elements.append(Paragraph("Key Findings", section_style))

        # Table header
        table_data = [["#", "Category", "Issue", "Severity", "Impact"]]

        # Take most important issues first (you can sort rows beforehand)
        for i, row in enumerate(rows[:15], 1):
            category = row.get("category", "General")
            issue = row.get("issue", "Unnamed issue")[:90]
            if len(row.get("issue", "")) > 90:
                issue += "..."

            severity = row.get("severity", "Medium").upper()
            impact = row.get("impact", row.get("score_impact", "—"))

            severity_color = {
                "CRITICAL": colors.red,
                "HIGH": colors.orange,
                "MEDIUM": colors.black,
                "LOW": colors.grey,
            }.get(severity, colors.black)

            table_data.append([
                str(i),
                category,
                issue,
                f"<font color='{severity_color.hexval()}'>{severity}</font>",
                str(impact)
            ])

        table = Table(table_data, colWidths=[0.8*cm, 3.2*cm, 7.5*cm, 2.8*cm, 2.2*cm])

        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.darkblue),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,0), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 11),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,1), (0,-1), 'CENTER'),  # # column
            ('ALIGN', (3,1), (3,-1), 'CENTER'),  # severity
        ]))

        elements.append(table)
        elements.append(Spacer(1, 1.2*cm))

    # ── Detailed Findings (if many issues) ────────────────────────────────────
    if len(rows) > 15:
        elements.append(PageBreak())
        elements.append(Paragraph("Detailed Findings", section_style))

        for i, row in enumerate(rows[15:], 16):
            issue_title = f"{i}. {row.get('issue', 'Unnamed finding')}"
            elements.append(Paragraph(issue_title, normal_style))

            if category := row.get("category"):
                elements.append(Paragraph(f"Category: {category}", small_style))

            if desc := row.get("description"):
                elements.append(Paragraph(f"Description: {desc}", normal_style))

            if reco := row.get("recommendation"):
                elements.append(Paragraph(f"Recommendation: {reco}", normal_style))

            elements.append(Spacer(1, 0.6*cm))

    # Generate PDF
    try:
        doc.build(elements)
        logger.info(f"PDF report successfully created: {pdf_path}")
        return pdf_path
    except Exception as e:
        logger.error("Failed to generate PDF report", exc_info=True)
        return None


def render_pdf_legacy(
    rows: List[Dict[str, Any]],
    output_dir: Path,
    logger
) -> Optional[Path]:
    """Compatibility wrapper - old simple version"""
    return render_pdf(rows, output_dir, logger)
