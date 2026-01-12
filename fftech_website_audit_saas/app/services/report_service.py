
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from .grader import compute_overall_grade
from ..config import LOGO_PATH, FFTECH_BRAND

BASE_REPORTS_DIR = Path(__file__).resolve().parent.parent / "static" / "reports"
BASE_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

def _chart_bar(category_scores: Dict[str, float], fname: Path) -> Path:
    cats = list(category_scores.keys())
    vals = [category_scores[k] for k in cats]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(cats, vals, color="#2c7be5")
    ax.set_ylim(0, 100)
    ax.set_title("Category Scores (%)")
    ax.set_ylabel("Score")
    plt.tight_layout()
    fig.savefig(fname)
    plt.close(fig)
    return fname


def generate_pdf_report(payload: Dict[str, Any]) -> Path:
    url = payload.get("url", "")
    category_scores = payload.get("category_scores", {})
    exec_summary = payload.get("executive_summary", {})
    overall_score, grade = compute_overall_grade(category_scores)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    pdf_path = BASE_REPORTS_DIR / (f"audit_{grade}_{int(datetime.utcnow().timestamp())}.pdf")
    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    if Path(LOGO_PATH).exists():
        story.append(Image(LOGO_PATH, width=120, height=120))
    story.append(Paragraph(f"<b>{FFTECH_BRAND}</b>", styles['Title']))
    story.append(Paragraph("Certified Website Audit Report", styles['h2']))
    story.append(Paragraph(f"URL: {url}", styles['Normal']))
    story.append(Paragraph(f"Generated: {now}", styles['Normal']))
    story.append(Paragraph(f"Overall Score: <b>{overall_score}%</b> &nbsp;&nbsp; Grade: <b>{grade}</b>", styles['h2']))
    story.append(Paragraph("Conclusion: The site demonstrates its current performance level based on available signals.", styles['Normal']))

    story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Executive Summary</b>", styles['h2']))
    story.append(Paragraph(f"Overall Site Health Score: {exec_summary.get('Overall Site Health Score (%)', 0)}%", styles['Normal']))
    story.append(Paragraph("Strengths:", styles['h3']))
    for s in exec_summary.get("Strengths", []):
        story.append(Paragraph(f"• {s}", styles['Normal']))
    story.append(Paragraph("Weaknesses:", styles['h3']))
    for w in exec_summary.get("Weaknesses", []):
        story.append(Paragraph(f"• {w}", styles['Normal']))
    story.append(Paragraph("Priority Fixes:", styles['h3']))
    for p in exec_summary.get("Priority Fixes", []):
        story.append(Paragraph(f"• {p}", styles['Normal']))
    story.append(Paragraph("Conclusion: Address priority fixes first to improve score and grade.", styles['Italic']))

    chart_path = BASE_REPORTS_DIR / "category_scores.png"
    _chart_bar(category_scores, chart_path)
    story.append(Spacer(1, 12))
    story.append(Image(str(chart_path), width=450, height=300))
    story.append(Paragraph("Conclusion: Focus on low-scoring categories for maximum ROI.", styles['Italic']))

    story.append(Spacer(1, 12))
    story.append(Paragraph("<b>On-page SEO Highlights</b>", styles['h2']))
    rows = [["Metric", "Value", "Score"]]
    for m in payload.get("metrics", [])[:10]:
        rows.append([m['name'], str(m['value']), str(m['score'])])
    tbl = Table(rows, colWidths=[220, 120, 80])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f0f4ff')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ALIGN', (1,1), (-1,-1), 'LEFT'),
    ]))
    story.append(tbl)
    story.append(Paragraph("Conclusion: Optimize title/meta, ensure a single H1, and add structured data.", styles['Italic']))

    story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Technical & Next Steps</b>", styles['h2']))
    story.append(Paragraph("Integrate Lighthouse/Web Vitals for LCP/FCP/CLS and schedule Railway Cron for periodic audits.", styles['Normal']))
    story.append(Paragraph("Conclusion: Implement fixes, re-run audits, and monitor trends.", styles['Italic']))

    doc.build(story)
    return pdf_path
