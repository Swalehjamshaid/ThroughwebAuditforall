
# fftech_audit/ui_and_pdf.py
import os
from io import BytesIO
from typing import List, Dict, Any
from dataclasses import dataclass

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

@dataclass
class Row:
    label: str
    value: float

def build_rows_for_ui(metrics: Dict[str, Any], cat: Dict[str, float]) -> List[Row]:
    return [
        Row("Performance", float(cat.get("Performance", 0.0))),
        Row("Mobile", float(cat.get("Mobile", 0.0))),
        Row("Accessibility", float(cat.get("Accessibility", 0.0))),
        Row("Security", float(cat.get("Security", 0.0))),
        Row("Indexing", float(cat.get("Indexing", 0.0))),
        Row("Metadata", float(cat.get("Metadata", 0.0))),
        Row("Structure", float(cat.get("Structure", 0.0))),
    ]

def _draw_wrapped_text(c: canvas.Canvas, text: str, x: float, y: float, max_width: float, leading=14):
    from reportlab.lib.utils import simpleSplit
    lines = simpleSplit(text or "", 'Helvetica', 11, max_width)
    for i, line in enumerate(lines):
        c.drawString(x, y - i * leading, line)
    return y - (len(lines) * leading)

def _chart_category_breakdown(cat: Dict[str, float]) -> BytesIO:
    buf = BytesIO()
    labels = list(cat.keys())
    values = [float(cat[k]) for k in labels]
    plt.figure(figsize=(6, 3.5), dpi=150)
    bars = plt.bar(labels, values, color="#667eea")
    plt.ylim(0, 100)
    plt.title("Category Breakdown (%)")
    plt.xticks(rotation=25, ha="right")
    for b, v in zip(bars, values):
        plt.text(b.get_x() + b.get_width()/2, b.get_height()+1, f"{v:.0f}%", ha="center", va="bottom", fontsize=8)
    plt.tight_layout()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf

def _chart_status_distribution(dist: Dict[int, int]) -> BytesIO:
    buf = BytesIO()
    labels = [str(k) for k in sorted(dist.keys())]
    values = [dist[k] for k in sorted(dist.keys())]
    plt.figure(figsize=(5.5, 3.2), dpi=150)
    plt.bar(labels, values, color="#00a86b")
    plt.title("HTTP Status Distribution")
    plt.xlabel("Bucket"); plt.ylabel("Count")
    plt.tight_layout()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf

def _safe_draw_logo(c: canvas.Canvas, path: str, x: float, y: float, w: float, h: float):
    """Draw logo only if present and readable; otherwise skip silently."""
    if not path or not os.path.exists(path):
        return
    try:
        img = ImageReader(path)  # validates file
        c.drawImage(img, x, y, width=w, height=h, preserveAspectRatio=True, mask='auto')
    except Exception:
        # Skip unreadable formats (e.g., webp) or corrupt files
        pass

def make_pdf_bytes(url: str, metrics: Dict[str, Any], rows: List[Row], charts: Dict[str, Any]) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # --- Page 1: Cover ---
    c.setFont("Helvetica-Bold", 22); c.setFillColor(colors.HexColor("#333"))
    c.drawString(72, h - 80, "FF Tech AI — Website Audit")
    c.setFont("Helvetica", 12)
    c.drawString(72, h - 105, f"Target: {url}")
    c.drawString(72, h - 120, f"Generated: {metrics.get('generated_at', '')} UTC")

    # Safe logo (PNG/JPEG recommended)
    logo_path = os.path.join(os.path.dirname(__file__), "static", "logo.png")
    _safe_draw_logo(c, logo_path, w - 180, h - 120, 96, 32)

    score = float(metrics.get("overall.health_score") or 0.0)
    c.setFont("Helvetica-Bold", 48); c.setFillColor(colors.HexColor("#667eea"))
    c.drawString(72, h - 180, f"{score:.1f}%")
    c.setFont("Helvetica-Bold", 32); c.setFillColor(colors.HexColor("#00a86b"))
    c.drawString(72, h - 220, f"Grade: {metrics.get('overall.grade', '—')}")
    c.setFont("Helvetica", 11)
    _draw_wrapped_text(c, "Conclusion: This page establishes the executive baseline—overall health score and grade.", 72, 140, w - 120)
    c.showPage()

    # --- Page 2: Executive Summary ---
    c.setFont("Helvetica-Bold", 18); c.drawString(72, h - 80, "Executive Summary")
    y = h - 120
    c.setFont("Helvetica", 11)
    y = _draw_wrapped_text(c, metrics.get("summary.executive", ""), 72, y, w - 120)
    y -= 20
    c.setFont("Helvetica-Bold", 14); c.drawString(72, y, "Strengths"); c.setFont("Helvetica", 11); y -= 18
    for s in metrics.get("summary.strengths", []) or ["No major strengths detected."]:
        y = _draw_wrapped_text(c, f"• {s}", 90, y, w - 160); y -= 4
    y -= 12; c.setFont("Helvetica-Bold", 14); c.drawString(72, y, "Weaknesses"); c.setFont("Helvetica", 11); y -= 18
    for s in metrics.get("summary.weaknesses", []) or ["No critical issues found."]:
        y = _draw_wrapped_text(c, f"• {s}", 90, y, w - 160); y -= 4
    y -= 12; c.setFont("Helvetica-Bold", 14); c.drawString(72, y, "Priority Fixes"); c.setFont("Helvetica", 11); y -= 18
    for i, s in enumerate(metrics.get("summary.priority_fixes", []) or ["Your site has strong foundations!"], 1):
        y = _draw_wrapped_text(c, f"{i}. {s}", 90, y, w - 160); y -= 4
    c.setFont("Helvetica", 11)
    _draw_wrapped_text(c, "Conclusion: Address Priority Fixes first to maximize impact on performance, SEO, and UX.", 72, 120, w - 120)
    c.showPage()

    # --- Page 3: Category Breakdown (chart) ---
    c.setFont("Helvetica-Bold", 18); c.drawString(72, h - 80, "Category Breakdown")
    cat = metrics.get("summary.category_breakdown", {}) or {}
    cat_buf = _chart_category_breakdown(cat)
    try:
        cat_img = ImageReader(cat_buf)
        c.drawImage(cat_img, 72, h - 360, width=380, height=220, preserveAspectRatio=True, mask='auto')
    except Exception:
        pass
    c.setFont("Helvetica", 12)
    y = h - 380
    for k, v in cat.items():
        c.drawString(72, y, f"{k}: {float(v):.1f}%"); y -= 18
    c.setFont("Helvetica", 11)
    _draw_wrapped_text(c, "Conclusion: Improving the lowest categories yields the fastest overall gains.", 72, 120, w - 120)
    c.showPage()

    # --- Page 4: Key Signals + status chart ---
    c.setFont("Helvetica-Bold", 18); c.drawString(72, h - 80, "Key Signals")
    c.setFont("Helvetica", 12)
    y = h - 120
    for r in rows:
        c.drawString(90, y, f"{r.label}: {float(r.value):.1f}%"); y -= 18
    dist = charts.get("status_distribution") or {}
    if dist:
        sd_buf = _chart_status_distribution(dist)
        try:
            sd_img = ImageReader(sd_buf)
            c.drawImage(sd_img, 72, 140, width=340, height=200, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    c.setFont("Helvetica", 11)
    _draw_wrapped_text(c, "Conclusion: Target signals under 70% in immediate sprints to unlock visible improvements.", 72, 120, w - 120)
    c.showPage()

    # --- Page 5: All Metrics (compact) ---
    c.setFont("Helvetica-Bold", 18); c.drawString(72, h - 80, "All Metrics (compact)")
    c.setFont("Helvetica", 11)
    y = h - 110
    for k in sorted(metrics.keys()):
        v = metrics[k]
        y = _draw_wrapped_text(c, f"{k}: {v}", 72, y, w - 120, leading=13); y -= 4
        if y < 100:
            c.showPage()
            c.setFont("Helvetica-Bold", 18); c.drawString(72, h - 80, "All Metrics (cont.)")
            c.setFont("Helvetica", 11); y = h - 110
    c.setFont("Helvetica", 11)
    _draw_wrapped_text(c, "Conclusion: This compact dataset supports engineering handoff and historical tracking.", 72, 80, w - 120)

    c.save()
    buf.seek(0)
    return buf.read()
