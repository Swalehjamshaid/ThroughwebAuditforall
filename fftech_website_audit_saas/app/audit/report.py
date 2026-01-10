
# app/audit/report.py
# -*- coding: utf-8 -*-
"""
FF Tech – Executive Website Audit v3 (10 pages)
Generates a multi‑page, executive‑grade PDF with gauges, radar charts, issue bars,
security heatmap, and competitor overlay.

Dependencies: reportlab, matplotlib, numpy
"""

import os
from datetime import datetime
from math import pi

import matplotlib.pyplot as plt
import numpy as np
import matplotlib.colors as mcolors

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak


# -------------------------- Chart helpers --------------------------

def _save_gauge(score: int, path: str, title: str = "Overall Health"):
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.set_aspect('equal')
    score = max(0, min(100, int(score)))
    wedges = [score, 100 - score]
    ax.pie(wedges, colors=['#10B981', '#EEEEEE'], startangle=90,
           counterclock=False, wedgeprops=dict(width=0.35, edgecolor='white'))
    ax.text(0, 0.02, f"{score}", ha='center', va='center',
            fontsize=20, fontweight='bold', color='#333')
    ax.text(0, -0.25, title, ha='center', va='center', fontsize=10, color='#666')
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches='tight')
    plt.close(fig)


def _save_cwv_micro(cwv: dict, path: str):
    metrics = ['LCP (s)', 'INP (ms)', 'CLS', 'TBT (ms)']
    values = [float(cwv.get('LCP', 0)), float(cwv.get('INP', 0)),
              float(cwv.get('CLS', 0)), float(cwv.get('TBT', 0))]
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.bar(metrics, values, color=['#10B981'] * 4)
    # Threshold lines
    ax.axhline(2.5, color='#F59E0B', lw=1, ls='--')
    ax.axhline(200, color='#F59E0B', lw=1, ls='--')
    ax.axhline(0.1, color='#F59E0B', lw=1, ls='--')
    ax.set_title('Core Web Vitals (lab + thresholds)')
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches='tight')
    plt.close(fig)


def _save_radar(labels, values, labels2, values2, path: str):
    labels = list(labels or [])
    values = list(values or [])
    N = len(labels) or 5
    if not labels:
        labels = ["Perf", "Acc", "SEO", "Sec", "BP"]
        values = [0] * 5
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    values_plot = values + values[:1]
    angles_plot = angles + angles[:1]
    fig = plt.figure(figsize=(4.8, 4.8))
    ax = fig.add_subplot(111, polar=True)
    ax.set_theta_offset(pi / 2)
    ax.set_theta_direction(-1)
    plt.xticks(angles, labels, fontsize=8)
    ax.set_rlabel_position(0)
    plt.yticks([20, 40, 60, 80, 100], ["20", "40", "60", "80", "100"], color="#666", size=7)
    plt.ylim(0, 100)
    ax.plot(angles_plot, values_plot, color='#4F46E5', linewidth=2)
    ax.fill(angles_plot, values_plot, color='#4F46E5', alpha=0.25)
    if labels2 and values2:
        v2 = list(values2) + list(values2[:1])
        ax.plot(angles_plot, v2, color='#EF4444', linewidth=2)
        ax.fill(angles_plot, v2, color='#EF4444', alpha=0.20)
    ax.set_title('Category Radar (Competitor overlay)', va='bottom')
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches='tight')
    plt.close(fig)


def _save_issues_bar(issues, path: str):
    labels, values = [], []
    for item in (issues or []):
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            labels.append(str(item[0]))
            values.append(int(item[1]))
        else:
            labels.append(str(item))
            values.append(1)
    if not labels:
        labels, values = ["No issues"], [0]
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.barh(labels, values, color='#F59E0B')
    ax.invert_yaxis()
    ax.set_title('Issue Frequency')
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches='tight')
    plt.close(fig)


def _save_security_heatmap(sec_dict: dict, path: str):
    keys = ["HSTS", "CSP", "XFO", "XCTO", "SSL_Valid", "MixedContent"]
    vals = [sec_dict.get(k, None) for k in keys]

    def to_score(v):
        if isinstance(v, bool):
            return 1 if v else 0
        if isinstance(v, str):
            return 1 if v.lower() in ("yes", "enabled", "valid", "pass") else 0
        return 0

    grid = np.array([to_score(v) for v in vals]).reshape(2, 3)
    fig, ax = plt.subplots(figsize=(4.8, 3.2))
    cmap = mcolors.ListedColormap(['#EF4444', '#10B981'])
    ax.imshow(grid, cmap=cmap, vmin=0, vmax=1)
    ax.set_xticks([0, 1, 2])
    ax.set_yticks([0, 1])
    ax.set_xticklabels(keys[0:3])
    ax.set_yticklabels(["", ""])
    for i in range(2):
        for j in range(3):
            label = keys[i * 3 + j]
            val = 'Pass' if grid[i, j] == 1 else 'Fail'
            ax.text(j, i, f"{label}\n{val}", ha='center', va='center', color='white', fontsize=8)
    ax.set_title('Security & Protocol Compliance')
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches='tight')
    plt.close(fig)


def _save_trend_line(labels, values, path: str):
    labels = list(labels or [])
    values = list(values or [])
    if not labels or not values:
        labels, values = ["Run"], [0]
    fig, ax = plt.subplots(figsize=(5.2, 3.2))
    ax.plot(labels, values, marker='o', color='#10B981')
    ax.set_ylim(0, 100)
    ax.set_title('Recent Health Trend')
    plt.grid(alpha=0.2)
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches='tight')
    plt.close(fig)


# -------------------------- PDF builder --------------------------

def render_pdf_10p(file_path: str, brand: str, site_url: str, grade: str,
                   health_score: int, category_scores, executive_summary: str = "",
                   cwv=None, top_issues=None, security=None, indexation=None,
                   competitor=None, trend=None):
    """Generate 10-page executive PDF with charts and competitor overlay."""
    img_dir = os.path.join("/tmp", "audit_imgs")
    os.makedirs(img_dir, exist_ok=True)

    def to_pairs(items):
        out = []
        for it in items or []:
            if isinstance(it, dict):
                out.append((str(it.get("name", "")), int(it.get("score", 0))))
            elif isinstance(it, (list, tuple)) and len(it) >= 2:
                out.append((str(it[0]), int(it[1])))
        return out

    cats = to_pairs(category_scores)
    labels = [n for n, _ in cats] or ["Performance", "Accessibility", "SEO", "Security", "BestPractices"]
    values = [s for _, s in cats] or [0, 0, 0, 0, 0]

    comp_labels, comp_values = None, None
    comp_url = None
    if competitor and isinstance(competitor, dict):
        comp_url = competitor.get("url")
        comp_pairs = to_pairs(competitor.get("category_scores", []))
        if comp_pairs:
            comp_labels = [n for n, _ in comp_pairs]
            comp_values = [s for _, s in comp_pairs]

    cwv = cwv or {}
    security = security or {}
    indexation = indexation or {}
    trend = trend or {"labels": [], "values": []}
    top_issues = top_issues or []

    # Generate charts
    img_gauge = os.path.join(img_dir, 'gauge.png'); _save_gauge(health_score, img_gauge)
    img_cwv = os.path.join(img_dir, 'cwv.png'); _save_cwv_micro(cwv, img_cwv)
    img_radar = os.path.join(img_dir, 'radar.png'); _save_radar(labels, values, comp_labels, comp_values, img_radar)
    img_issues = os.path.join(img_dir, 'issues.png'); _save_issues_bar(top_issues, img_issues)
    img_sec = os.path.join(img_dir, 'security.png'); _save_security_heatmap(security, img_sec)
    img_trend = os.path.join(img_dir, 'trend.png'); _save_trend_line(trend.get("labels", []), trend.get("values", []), img_trend)

    # PDF styles
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='H1', fontSize=18, leading=22, spaceAfter=12, textColor=colors.HexColor('#4F46E5')))
    styles.add(ParagraphStyle(name='H2', fontSize=14, leading=18, spaceAfter=8, textColor=colors.HexColor('#10B981')))
    styles.add(ParagraphStyle(name='Body', fontSize=10, leading=14, spaceAfter=6))
    styles.add(ParagraphStyle(name='Small', fontSize=8, leading=12, textColor=colors.grey))

    story = []
    doc = SimpleDocTemplate(file_path, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm)

    # Pages
    story.append(Paragraph(f"{brand} – Executive Website Audit", styles['H1']))
    story.append(Paragraph(f"Site: {site_url}", styles['Body']))
    if comp_url: story.append(Paragraph(f"Competitor: {comp_url}", styles['Body']))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Executive Overview", styles['H2']))
    story.append(Paragraph(executive_summary or "Summary of technical health, CWV, security, indexation, accessibility.", styles['Body']))
    story.append(Image(img_trend, width=12 * cm, height=7 * cm)); story.append(PageBreak())

    story.append(Paragraph("KPIs & Overall Health Gauge", styles['H2']))
    story.append(Image(img_gauge, width=10 * cm, height=10 * cm)); story.append(PageBreak())

    story.append(Paragraph("Core Web Vitals", styles['H2']))
    story.append(Image(img_cwv, width=15 * cm, height=7 * cm)); story.append(PageBreak())

    story.append(Paragraph("Category Radar", styles['H2']))
    story.append(Image(img_radar, width=12.5 * cm, height=12.5 * cm)); story.append(PageBreak())

    story.append(Paragraph("Top Issues", styles['H2']))
    story.append(Image(img_issues, width=15 * cm, height=7 * cm)); story.append(PageBreak())

    story.append(Paragraph("Security Compliance", styles['H2']))
    story.append(Image(img_sec, width=12 * cm, height=8 * cm)); story.append(PageBreak())

    story.append(Paragraph("Indexation & Canonicalization", styles['H2']))
    story.append(Paragraph(f"robots.txt: {indexation.get('robots_txt', 'N/A')}", styles['Body'])); story.append(PageBreak())

    story.append(Paragraph("Performance Delivery", styles['H2']))
    story.append(Paragraph("Enable Brotli + Gzip fallback; set Vary: Accept-Encoding.", styles['Body'])); story.append(PageBreak())

    story.append(Paragraph("Accessibility (WCAG 2.2)", styles['H2']))
    story.append(Paragraph("Improve focus visibility, target size, accessible auth.", styles['Body'])); story.append(PageBreak())

    story.append(Paragraph("References & Roadmap", styles['H2']))
    story.append(Paragraph(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} • {brand}", styles['Small']))

    doc.build(story)


# -------------------------- Backward-compatible wrapper --------------------------

def render_pdf(file_path: str, brand: str, site_url: str, grade: str,
               health_score: int, category_scores, executive_summary: str):
    """Legacy wrapper for existing calls."""
    render_pdf_10p(file_path, brand, site_url, grade, health_score,
                   category_scores, executive_summary)
