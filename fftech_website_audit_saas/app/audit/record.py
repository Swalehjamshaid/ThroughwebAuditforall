
from __future__ import annotations
from pathlib import Path
from typing import Dict, Any
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    from pptx import Presentation
    from pptx.util import Inches
except ModuleNotFoundError:
    Presentation = None

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font
except ModuleNotFoundError:
    Workbook = None

BASE_EXPORT_DIR = Path(__file__).resolve().parent.parent / "static" / "exports"
BASE_EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def _scores(data: Dict[str, float] | None) -> Dict[str, float]:
    cats = list("ABCDEFGHI")
    return {k: float(data.get(k, 0.0)) if data else 0.0 for k in cats}


def render_dashboard_png(category_scores: Dict[str, float] | None = None) -> Path:
    d = _scores(category_scores)
    png_path = BASE_EXPORT_DIR / "dashboard.png"
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(list(d.keys()), list(d.values()), color="#2c7be5")
    ax.set_ylim(0, 100)
    ax.set_title("Category Scores (%)")
    ax.set_ylabel("Score")
    plt.tight_layout()
    fig.savefig(png_path)
    plt.close(fig)
    return png_path


def export_ppt(payload: Dict[str, Any]) -> Path:
    chart_path = render_dashboard_png(payload.get("category_scores"))
    ppt_path = BASE_EXPORT_DIR / "audit_report.pptx"
    if Presentation is None:
        return chart_path
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "FF Tech AI Website Audit"
    slide.placeholders[1].text = f"URL: {payload.get('url','')} | Grade: {payload.get('overall',{}).get('grade','')} | Score: {payload.get('overall',{}).get('score','')}%"
    slide2 = prs.slides.add_slide(prs.slide_layouts[6])
    slide2.shapes.add_picture(str(chart_path), Inches(1), Inches(1), width=Inches(8))
    prs.save(ppt_path)
    return ppt_path


def export_xlsx(payload: Dict[str, Any]) -> Path:
    xlsx_path = BASE_EXPORT_DIR / "audit_report.xlsx"
    if Workbook is None:
        return render_dashboard_png(payload.get("category_scores"))
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws["A1"].value = "FF Tech AI Website Audit"
    ws["A1"].font = Font(bold=True, size=14)
    ws.append(["URL", payload.get("url", "")])
    overall = payload.get("overall", {})
    ws.append(["Overall Score", overall.get("score", 0)])
    ws.append(["Grade", overall.get("grade", "")])
    ws.append([])
    ws.append(["Category", "Score (%)"]) 
    for k, v in _scores(payload.get("category_scores")).items():
        ws.append([k, v])
    ws2 = wb.create_sheet("Metrics")
    ws2.append(["ID", "Name", "Value", "Score", "Status"]) 
    for m in payload.get("metrics", [])[:200]:
        ws2.append([m.get("id"), m.get("name"), str(m.get("value")), m.get("score"), m.get("status")])
    wb.save(xlsx_path)
    return xlsx_path
