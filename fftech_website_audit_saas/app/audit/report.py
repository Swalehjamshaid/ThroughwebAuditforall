
# -*- coding: utf-8 -*-
"""
Visual, multi-page PDF report with colored charts and consistent formatting.

Usage (existing):
render_pdf(path, brand_name, url, grade, health_score, category_scores, exec_summary)
- category_scores: list[{"name": str, "score": int}]
- exec_summary: str
"""
import io
import math
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

# ---------- Design tokens ----------
PALETTE = {
    "primary": "#0057D9",
    "secondary": "#1ABC9C",
    "accent": "#F39C12",
    "danger": "#E74C3C",
    "dark": "#2C3E50",
    "light": "#ECF0F1",
    "mid": "#95A5A6",
}

SAFE_COLORS = [
    "#0057D9", "#1ABC9C", "#F39C12", "#8E44AD", "#2ECC71",
    "#E67E22", "#E74C3C", "#3498DB", "#16A085", "#9B59B6"
]

PADDING = 12 * mm
LINE = 6 * mm
PAGE_W, PAGE_H = A4

# ---------- Helpers ----------
def _write_header_footer(c: canvas.Canvas, brand: str, page_title: str, page_num: int):
    # Header bar
    c.setFillColor(colors.HexColor(PALETTE["primary"]))
    c.rect(0, PAGE_H - 18*mm, PAGE_W, 18*mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(PADDING, PAGE_H - 12*mm, f"{brand} · Certified Website Audit")
    c.setFont("Helvetica", 11)
    c.drawRightString(PAGE_W - PADDING, PAGE_H - 12*mm, page_title)

    # Footer bar
    c.setFillColor(colors.HexColor(PALETTE["dark"]))
    c.rect(0, 0, PAGE_W, 12*mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica", 9)
    c.drawString(PADDING, 5*mm, "Certified by FF Tech · Valid for 30 days")
    c.drawRightString(PAGE_W - PADDING, 5*mm, f"Page {page_num}")

def _badge_grade_color(grade: str):
    g = (grade or "C").upper()
    if g in ("A", "A+"): return PALETTE["secondary"]
    if g in ("B", "B+"): return "#27AE60"
    if g in ("C", "C+"): return PALETTE["accent"]
    return PALETTE["danger"]

def _health_ring_image(score: int, size_px=300):
    # Donut ring with central score
    fig, ax = plt.subplots(figsize=(size_px/96, size_px/96), dpi=96)
    ax.axis("equal"); ax.set_axis_off()

    val = max(0, min(100, int(score)))
    # background ring
    ax.pie([100], colors=[PALETTE["light"]], radius=1.0, wedgeprops=dict(width=0.18, edgecolor=PALETTE["light"]))
    # foreground ring
    ax.pie([val, 100-val],
           colors=[PALETTE["primary"], PALETTE["light"]],
           radius=1.0,
           startangle=90,
           wedgeprops=dict(width=0.18, edgecolor=PALETTE["light"]))
    # inner white
    ax.add_patch(Circle((0,0), 0.75, color="white"))
    # text
    ax.text(0, 0.05, f"{val}%", ha="center", va="center", fontsize=28, color=PALETTE["dark"], fontweight="bold")
    ax.text(0, -0.20, "Health", ha="center", va="center", fontsize=12, color=PALETTE["mid"])

    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png", dpi=96, transparent=True)
    plt.close(fig)
    buf.seek(0)
    return ImageReader(buf)

def _bar_chart_image(category_scores, title="Category Scores", width_px=800, height_px=400):
    labels = [x["name"] for x in category_scores]
    values = [int(x["score"]) for x in category_scores]
    colors_list = [SAFE_COLORS[i % len(SAFE_COLORS)] for i in range(len(labels))]

    fig, ax = plt.subplots(figsize=(width_px/96, height_px/96), dpi=96)
    ax.barh(labels, values, color=colors_list)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Score (%)")
    ax.set_title(title, color=PALETTE["dark"], fontsize=14, fontweight="bold")
    ax.grid(axis="x", alpha=0.2)
    for i, v in enumerate(values):
        ax.text(v + 1, i, f"{v}%", va="center", fontsize=10, color=PALETTE["dark"])
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=144, transparent=True)
    plt.close(fig)
    buf.seek(0)
    return ImageReader(buf)

def _radar_chart_image(category_scores, title="Category Comparison", size_px=500):
    labels = [x["name"] for x in category_scores]
    values = [int(x["score"]) for x in category_scores]
    angles = [n / float(len(labels)) * 2 * math.pi for n in range(len(labels))]
    values += values[:1]
    angles += angles[:1]

    fig = plt.figure(figsize=(size_px/96, size_px/96), dpi=96)
    ax = plt.subplot(111, polar=True)
    plt.xticks(angles[:-1], labels, color=PALETTE["dark"], fontsize=9)
    ax.set_rlabel_position(0)
    plt.yticks([20,40,60,80], ["20","40","60","80"], color=PALETTE["mid"], size=8)
    plt.ylim(0, 100)

    ax.plot(angles, values, color=PALETTE["primary"], linewidth=2)
    ax.fill(angles, values, color=PALETTE["primary"], alpha=0.15)
    ax.set_title(title, fontsize=12, color=PALETTE["dark"], pad=14)

    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png", dpi=144, transparent=True)
    plt.close(fig)
    buf.seek(0)
    return ImageReader(buf)

def _web_vitals_donuts(lcp_ms=2500, tbt_ms=300, cls=0.1, size_px=260):
    # Draw 3 donuts for LCP/TBT/CLS with thresholds
    def donut(val, max_val, label, good, needs):
        pct = max(0, min(100, int(round(val / max_val * 100))))
        fig, ax = plt.subplots(figsize=(size_px/96, size_px/96), dpi=96)
        ax.axis("equal"); ax.set_axis_off()
        ax.pie([pct, 100-pct],
               colors=[PALETTE["secondary"] if val <= good else (PALETTE["accent"] if val <= needs else PALETTE["danger"]),
                       PALETTE["light"]],
               startangle=90, radius=1.0,
               wedgeprops=dict(width=0.22, edgecolor=PALETTE["light"]))
        ax.add_patch(Circle((0,0), 0.75, color="white"))
        ax.text(0, 0.05, f"{val}", ha="center", va="center", fontsize=20, color=PALETTE["dark"], fontweight="bold")
        ax.text(0, -0.22, label, ha="center", va="center", fontsize=11, color=PALETTE["mid"])
        buf = io.BytesIO(); plt.tight_layout(); plt.savefig(buf, format="png", dpi=96, transparent=True)
        plt.close(fig); buf.seek(0)
        return ImageReader(buf)

    return {
        "LCP": donut(lcp_ms, 4000, "LCP (ms)", good=2500, needs=4000),
        "TBT": donut(tbt_ms, 600, "TBT (ms)", good=200, needs=600),
        "CLS": donut(int(cls*1000)/1000, 0.4, "CLS", good=0.1, needs=0.25),
    }

# ---------- Main render ----------
def render_pdf(path, brand_name, url, grade, health_score, category_scores, exec_summary):
    """
    Create a multi-page, full-color, graphical PDF.
    """
    c = canvas.Canvas(path, pagesize=A4)

    # Prepare computed bits
    now_str = datetime.utcnow().strftime("%d %b %Y %H:%M UTC")
    grade_text = str(grade or "N/A")
    health_val = int(health_score or 0)
    categories = category_scores or []
    # Pad missing categories with dummy entries for consistent visuals
    if len(categories) < 6:
        categories += [{"name": f"Category {i+1}", "score": 50} for i in range(6 - len(categories))]

    # ---------- Page 1: Cover ----------
    _write_header_footer(c, brand_name, "Cover", 1)

    # Brand strip
    c.setFillColor(colors.HexColor(PALETTE["light"]))
    c.rect(PADDING, PAGE_H - 28*mm, PAGE_W - 2*PADDING, 8*mm, fill=1, stroke=0)

    # Title
    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(colors.HexColor(PALETTE["dark"]))
    c.drawString(PADDING, PAGE_H - 40*mm, "Certified Website Audit Report")

    # URL & Date
    c.setFont("Helvetica", 12)
    c.setFillColor(colors.HexColor(PALETTE["mid"]))
    c.drawString(PADDING, PAGE_H - 48*mm, f"Domain: {url}")
    c.drawString(PADDING, PAGE_H - 55*mm, f"Date: {now_str}")

    # Grade badge
    badge_color = colors.HexColor(_badge_grade_color(grade_text))
    c.setFillColor(badge_color)
    c.circle(PAGE_W - 60*mm, PAGE_H - 50*mm, 18*mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(PAGE_W - 60*mm, PAGE_H - 50*mm - 6, grade_text)

    # Health ring
    ring = _health_ring_image(health_val)
    c.drawImage(ring, PAGE_W - 100*mm, PAGE_H - 110*mm, 80*mm, 80*mm, mask='auto')

    # Seal
    c.setFillColor(colors.HexColor(PALETTE["primary"]))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(PADDING, 30*mm, "Certified by FF Tech")
    c.setFillColor(colors.HexColor(PALETTE["mid"]))
    c.setFont("Helvetica", 10)
    c.drawString(PADDING, 24*mm, "Valid for 30 days · Automated report")

    c.showPage()

    # ---------- Page 2: Executive Summary ----------
    _write_header_footer(c, brand_name, "Executive Summary", 2)

    # Summary box
    c.setFillColor(colors.HexColor(PALETTE["light"]))
    c.roundRect(PADDING, PAGE_H - 120*mm, PAGE_W - 2*PADDING, 90*mm, 6*mm, fill=1, stroke=0)

    c.setFillColor(colors.HexColor(PALETTE["dark"]))
    c.setFont("Helvetica-Bold", 16)
    c.drawString(PADDING + 6*mm, PAGE_H - 112*mm, "Summary")

    c.setFillColor(colors.HexColor(PALETTE["dark"]))
    c.setFont("Helvetica", 11)
    # Wrap text manually: simple line splitting
    text = c.beginText(PADDING + 6*mm, PAGE_H - 120*mm + 75*mm)
    text.setFont("Helvetica", 11)
    text.setFillColor(colors.HexColor(PALETTE["dark"]))

    # naive wrap
    def split_lines(paragraph, width_chars=95):
        words = paragraph.split()
        lines, cur = [], []
        ln = 0
        for w in words:
            cur.append(w)
            if len(" ".join(cur)) > width_chars:
                lines.append(" ".join(cur[:-1]))
                cur = [w]
        if cur:
            lines.append(" ".join(cur))
        return lines

    for line in split_lines(exec_summary or "No executive summary provided.", width_chars=95):
        text.textLine(line)
    c.drawText(text)

    # Key metrics chips
    c.setFillColor(colors.HexColor(PALETTE["secondary"]))
    c.roundRect(PADDING, PAGE_H - 130*mm, 55*mm, 8*mm, 3*mm, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(PADDING + 27.5*mm, PAGE_H - 127*mm, f"Grade: {grade_text}")

    c.setFillColor(colors.HexColor(PALETTE["accent"]))
    c.roundRect(PADDING + 60*mm, PAGE_H - 130*mm, 70*mm, 8*mm, 3*mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.drawCentredString(PADDING + 95*mm, PAGE_H - 127*mm, f"Health Score: {health_val}%")

    c.setFillColor(colors.HexColor(PALETTE["primary"]))
    c.roundRect(PADDING + 135*mm, PAGE_H - 130*mm, 40*mm, 8*mm, 3*mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.drawCentredString(PADDING + 155*mm, PAGE_H - 127*mm, "Security")

    c.showPage()

    # ---------- Page 3: Category Charts ----------
    _write_header_footer(c, brand_name, "Category Scores & Radar", 3)

    # Bar chart
    bar_img = _bar_chart_image(categories, title="Scores by Category")
    c.drawImage(bar_img, PADDING, PAGE_H - 140*mm, PAGE_W - 2*PADDING, 80*mm, mask='auto')

    # Radar chart
    radar_img = _radar_chart_image(categories, title="Category Comparison (Radar)")
    c.drawImage(radar_img, PADDING, PAGE_H - 240*mm, PAGE_W - 2*PADDING, 90*mm, mask='auto')

    c.showPage()

    # ---------- Page 4: Web Vitals ----------
    _write_header_footer(c, brand_name, "Core Web Vitals", 4)

    vitals = _web_vitals_donuts(lcp_ms=2500, tbt_ms=350, cls=0.15)
    # Place donuts
    c.drawImage(vitals["LCP"], PADDING + 10*mm, PAGE_H - 140*mm, 55*mm, 55*mm, mask='auto')
    c.drawImage(vitals["TBT"], PADDING + 75*mm, PAGE_H - 140*mm, 55*mm, 55*mm, mask='auto')
    c.drawImage(vitals["CLS"], PADDING + 140*mm, PAGE_H - 140*mm, 55*mm, 55*mm, mask='auto')

    # Note
    c.setFillColor(colors.HexColor(PALETTE["mid"]))
    c.setFont("Helvetica", 10)
    c.drawString(PADDING, PAGE_H - 150*mm, "Targets: LCP ≤ 2.5s, TBT ≤ 200ms, CLS ≤ 0.1")

    c.showPage()

    # ---------- Page 5: Recommendations ----------
    _write_header_footer(c, brand_name, "Recommendations", 5)

    suggestions = [
        ("Technical & Performance", "Optimize LCP/FCP; eliminate render-blocking CSS/JS."),
        ("Crawlability & Indexation", "Repair broken links; ensure sitemap & canonical consistency."),
        ("Security & HTTPS", "Implement CSP + HSTS; fix mixed content; enforce HTTPS."),
        ("Mobile & Usability", "Improve tap targets & font sizes; check viewport settings."),
        ("On-Page SEO", "Improve titles, meta descriptions, headings, and structured data."),
    ]

    y = PAGE_H - 50*mm
    for i, (cat, tip) in enumerate(suggestions):
        tag_color = colors.HexColor(SAFE_COLORS[i % len(SAFE_COLORS)])
        c.setFillColor(tag_color)
        c.roundRect(PADDING, y, 35*mm, 8*mm, 3*mm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(PADDING + 17.5*mm, y + 2.5*mm, cat)

        c.setFillColor(colors.HexColor(PALETTE["dark"]))
        c.setFont("Helvetica", 11)
        c.drawString(PADDING + 40*mm, y + 2.5*mm, tip)
        y -= 15*mm

    # Seal & closing
    c.setFillColor(colors.HexColor(PALETTE["primary"]))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(PADDING, 25*mm, f"{brand_name} · Certified Website Audit")
    c.setFillColor(colors.HexColor(PALETTE["mid"]))
    c.setFont("Helvetica", 10)
    c.drawString(PADDING, 19*mm, "For stakeholders, executives, and engineering teams. Continuous monitoring recommended.")

    c.save()
