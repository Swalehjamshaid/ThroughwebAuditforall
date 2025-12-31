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
        c.drawImage(img, x, y, width=w, height=h, mask='auto')
    except Exception:
        pass

# ... (truncated 2189 characters; assume complete in local) ...
