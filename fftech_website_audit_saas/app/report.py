
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.units import cm
from reportlab.lib import colors

TZ_OFFSET = timezone(timedelta(hours=5))


def build_report(audit_ctx: Dict[str, Any], output_dir: str, formats: list[str] = ["pdf"], title: str = "Website Audit Report", author: str = "FF Tech") -> dict[str, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"audit_{datetime.now(TZ_OFFSET).strftime('%Y%m%d_%H%M%S')}.pdf"

    c = Canvas(str(pdf_path), pagesize=A4)
    width, height = A4

    def header(page_title: str):
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(2*cm, height-2*cm, f"FF Tech · {page_title}")
        c.setFont("Helvetica", 9)
        c.drawString(2*cm, height-2.8*cm, f"Generated: {datetime.now(TZ_OFFSET).isoformat()}")
        c.line(2*cm, height-3*cm, width-2*cm, height-3*cm)

    header("Executive Summary")
    c.setFont("Helvetica", 12)
    c.drawString(2*cm, height-4*cm, f"URL: {audit_ctx.get('url','')}")
    c.drawString(2*cm, height-5*cm, f"Score: {audit_ctx.get('overall_score',0)}% · Grade: {audit_ctx.get('overall_grade','-')}")
    text = c.beginText(2*cm, height-6*cm)
    text.textLines(audit_ctx.get('executive_summary',{}).get('summary',''))
    c.drawText(text)
    c.showPage()

    header("Category Breakdown")
    y = height - 5*cm
    for cat, val in audit_ctx.get('executive_summary',{}).get('category_breakdown',{}).items():
        c.drawString(2*cm, y, cat)
        c.setFillColor(colors.HexColor('#6c5ce7'))
        c.rect(6*cm, y-0.3*cm, (val/100)*(width-8*cm), 0.5*cm, fill=True, stroke=False)
        c.setFillColor(colors.black)
        c.drawString(width-2.5*cm, y, f"{val}%")
        y -= 1*cm
    c.showPage()

    header("Strengths & Weak Areas")
    c.setFont("Helvetica", 11)
    c.drawString(2*cm, height-4*cm, "Strengths:")
    y = height - 5*cm
    for s in audit_ctx.get('executive_summary',{}).get('strengths',[]):
        c.drawString(2.5*cm, y, f"• {s}")
        y -= 0.7*cm
    c.drawString(2*cm, y-0.7*cm, "Weak Areas:")
    y -= 1.4*cm
    for w in audit_ctx.get('executive_summary',{}).get('weak_areas',[]):
        c.drawString(2.5*cm, y, f"• {w}")
        y -= 0.7*cm
    c.showPage()

    header("Priority Fixes & Trends")
    c.setFont("Helvetica", 11)
    c.drawString(2*cm, height-4*cm, "Priority Fixes:")
    y = height - 5*cm
    for p in audit_ctx.get('executive_summary',{}).get('priority_fixes',[]):
        c.drawString(2.5*cm, y, f"• {p}")
        y -= 0.7*cm
    c.setFont("Helvetica", 10)
    c.drawString(2*cm, y-1.0*cm, "Issues Trend (recent):")
    y -= 2.0*cm
    trend = audit_ctx.get('overall_site_health',{}).get('issues_trend',[])
    for i, v in enumerate(trend):
        c.setFillColor(colors.HexColor('#00d4ff'))
        c.rect(3*cm + i*2*cm, y, 1.2*cm, v*0.2*cm, fill=True, stroke=False)
    c.setFillColor(colors.black)
    c.showPage()

    header("Conclusion")
    c.setFont("Helvetica", 12)
    c.drawString(2*cm, height-4*cm, "Client-ready, executive-friendly, printable.")
    c.setFont("Helvetica", 10)
    c.drawString(2*cm, height-5*cm, "FF Tech branding & certified export readiness")
    c.drawString(2*cm, height-6*cm, f"Overall Grade: {audit_ctx.get('overall_grade','-')}")
    c.drawString(2*cm, height-7*cm, f"Crawled Pages: {audit_ctx.get('overall_site_health',{}).get('total_crawled_pages','-')}")
    c.save()

    return {'report_pdf': str(pdf_path)}
