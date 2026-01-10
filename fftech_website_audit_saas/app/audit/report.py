
# app/audit/report.py
# -*- coding: utf-8 -*-
"""
FF Tech – Executive Website Audit v3 (10 pages)
Generates a multi‑page, executive‑grade PDF with gauges, radar charts, issue bars,
security heatmap, and competitor overlay.

Dependencies: reportlab, matplotlib, numpy (all standard in your environment).
No network access is required.
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
    """Donut gauge for overall health."""
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.set_aspect('equal')
    val = max(0, min(100, int(score)))
    wedges = [val, 100 - val]
    ax.pie(
        wedges,
        colors=['#10B981', '#EEEEEE'],
        startangle=90,
        counterclock=False,
        wedgeprops=dict(width=0.35, edgecolor='white')
    )
    ax.text(0, 0.02, f"{val}", ha='center', va='center',
            fontsize=20, fontweight='bold', color='#333')
    ax.text(0, -0.25, title, ha='center', va='center', fontsize=10, color='#666')
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches='tight')
    plt.close(fig)


def _save_cwv_micro(cwv: dict, path: str):
    """Small bars for LCP/INP/CLS/TBT with threshold markers."""
    LCP = float(cwv.get('LCP', 0))     # seconds
    INP = float(cwv.get('INP', 0))     # ms
    CLS = float(cwv.get('CLS', 0))     # unitless
    TBT = float(cwv.get('TBT', 0))     # ms

    metrics = ['LCP (s)', 'INP (ms)', 'CLS', 'TBT (ms)']
    values = [LCP, INP, CLS, TBT]

    fig, ax = plt.subplots(figsize=(6, 3))
    ax.bar(metrics, values, color=['#10B981'] * 4)

    # Threshold lines (Google guidance)
    # LCP ≤ 2.5s, INP ≤ 200ms, CLS ≤ 0.1, (lab TBT ≤ 200ms)
    ax.axhline(2.5, color='#F59E0B', lw=1, ls='--'); ax.text(-0.4, 2.5, 'LCP ≤2.5s', fontsize=8, color='#F59E0B')
    ax.axhline(200, color='#F59E0B', lw=1, ls='--'); ax.text(0.8, 200, 'INP ≤200ms', fontsize=8, color='#F59E0B')
    ax.axhline(0.1, color='#F59E0B', lw=1, ls='--'); ax.text(1.8, 0.1, 'CLS ≤0.1', fontsize=8, color='#F59E0B')
    ax.axhline(200, color='#F59E0B', lw=1, ls='--'); ax.text(2.8, 200, 'TBT ≤200ms', fontsize=8, color='#F59E0B')

    ax.set_ylabel('Value')
    ax.set_title('Core Web Vitals (lab + thresholds)')
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches='tight')
    plt.close(fig)


def _save_radar(labels, values, labels2, values2, path: str):
    """Radar chart; overlays competitor if provided."""
    labels = list(labels or [])
    values = list(values or [])
    N = len(labels)
    if N == 0:
        labels = ["Performance", "Accessibility", "SEO", "Security", "BestPractices"]
        values = [0, 0, 0, 0, 0]
        N = 5

    # angles
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
    """Horizontal bar for issue frequency."""
    # Accept ["issue1", "issue2"] or [("issue1", 12), ...]
    labels, values = [], []
    for item in (issues or []):
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            labels.append(str(item[0]))
            values.append(int(item[1]))
        else:
            labels.append(str(item))
            values.append(1)

    if not labels:
        labels, values = ["No issues provided"], [0]

    fig, ax = plt.subplots(figsize=(6, 3))
    ax.barh(labels, values, color='#F59E0B')
    ax.invert_yaxis()
    ax.set_xlabel('Frequency')
    ax.set_title('Issue Frequency (top items)')
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches='tight')
    plt.close(fig)


def _save_security_heatmap(sec_dict: dict, path: str):
    """2x3 heatmap: HSTS, CSP, XFO / XCTO, SSL_Valid, MixedContent."""
    keys = ["HSTS", "CSP", "XFO", "XCTO", "SSL_Valid", "MixedContent"]
    vals = [sec_dict.get(k, None) for k in keys]

    def to_score(v):
        if isinstance(v, bool):
            return 1 if v else 0
        if isinstance(v, str):
            v_lower = v.lower()
            if v_lower in ("yes", "enabled", "valid", "pass"):
                return 1
            if v_lower in ("no", "disabled", "fail"):
                return 0
        return 0  # unknown -> fail (visually prompts action)

    grid = np.array([to_score(v) for v in vals]).reshape(2, 3)

    fig, ax = plt.subplots(figsize=(4.8, 3.2))
    cmap = mcolors.ListedColormap(['#EF4444', '#10B981'])  # red fail, green pass
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

    ax.set_title('Security & Protocol Compliance (Pass/Fail)')
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches='tight')
    plt.close(fig)


def _save_trend_line(labels, values, path: str):
    labels = list(labels or [])
    values = list(values or [])
    if not labels or not values:
        labels, values = ["Run 1"], [0]

    fig, ax = plt.subplots(figsize=(5.2, 3.2))
    ax.plot(labels, values, marker='o', color='#10B981')
    ax.set_ylim(0, 100)
    ax.set_ylabel('Health')
    ax.set_title('Recent Health Trend')
    plt.grid(alpha=0.2)
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches='tight')
    plt.close(fig)


# -------------------------- 10‑page PDF builder --------------------------

def render_pdf_10p(
    file_path: str,
    brand: str,
    site_url: str,
    grade: str,
    health_score: int,
    category_scores,                 # list[dict{name, score}] or list[(name, score)]
    executive_summary: str = "",
    cwv: dict | None = None,
    top_issues: list | None = None,
    security: dict | None = None,
    indexation: dict | None = None,
    competitor: dict | None = None,  # {"url": str, "category_scores": list[dict{name, score}]}
    trend: dict | None = None        # {"labels": [...], "values": [...]}
):
    """
    Build a 10‑page executive PDF with charts and competitor overlay.
    This function is robust to missing data and will show helpful placeholders.
    """

    # Prepare working image directory
    img_dir = os.path.join("/tmp", "audit_imgs")
    os.makedirs(img_dir, exist_ok=True)

    # Normalize categories for radar
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

    # CWV / Security / Indexation / Trend defaults
    cwv = cwv or {}
    security = security or {}
    indexation = indexation or {}
    trend = trend or {"labels": [], "values": []}
    top_issues = top_issues or []

    # Generate charts
    img_gauge = os.path.join(img_dir, 'gauge.png')
    _save_gauge(health_score, img_gauge)

    img_cwv = os.path.join(img_dir, 'cwv.png')
    _save_cwv_micro(cwv, img_cwv)

    img_radar = os.path.join(img_dir, 'radar.png')
    _save_radar(labels, values, comp_labels, comp_values, img_radar)

    img_issues = os.path.join(img_dir, 'issues.png')
    _save_issues_bar(top_issues, img_issues)

    img_sec = os.path.join(img_dir, 'security.png')
    _save_security_heatmap(security, img_sec)

    img_trend = os.path.join(img_dir, 'trend.png')
    _save_trend_line(trend.get("labels", []), trend.get("values", []), img_trend)

    # PDF styles
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='H1', fontSize=18, leading=22, spaceAfter=12,
                              textColor=colors.HexColor('#4F46E5')))
    styles.add(ParagraphStyle(name='H2', fontSize=14, leading=18, spaceAfter=8,
                              textColor=colors.HexColor('#10B981')))
    styles.add(ParagraphStyle(name='Body', fontSize=10, leading=14, spaceAfter=6))
    styles.add(ParagraphStyle(name='Small', fontSize=8, leading=12, textColor=colors.grey))

    story = []
    doc = SimpleDocTemplate(file_path, pagesize=A4,
                            leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm)

    # Page 1 – Cover & executive overview
    story.append(Paragraph(f"{brand} – Executive Website Audit (v3, 10 pages)", styles['H1']))
    story.append(Paragraph(f"Site: {site_url}", styles['Body']))
    if comp_url:
        story.append(Paragraph(f"Competitor: {comp_url}", styles['Body']))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Executive Overview", styles['H2']))
    story.append(Paragraph(executive_summary or
                           "This report summarizes technical health, performance, security, "
                           "indexation, accessibility (WCAG 2.2), and competitive positioning.",
                           styles['Body']))
    story.append(Spacer(1, 12))
    story.append(Image(img_trend, width=12 * cm, height=7 * cm))
    story.append(Paragraph("Trend: recent health scores across audits.", styles['Small']))
    story.append(PageBreak())

    # Page 2 – KPI & Gauge
    story.append(Paragraph("KPIs & Overall Health Gauge", styles['H2']))
    story.append(Paragraph(f"Grade: {grade} • Overall Health: {int(health_score)}/100.", styles['Body']))
    story.append(Image(img_gauge, width=10 * cm, height=10 * cm))
    story.append(PageBreak())

    # Page 3 – Core Web Vitals
    story.append(Paragraph("Core Web Vitals (CWV)", styles['H2']))
    story.append(Paragraph(
        "Targets: LCP ≤ 2.5s, INP ≤ 200ms, CLS ≤ 0.1. "
        "Use TBT (lab) to triage main‑thread blocking.",
        styles['Body']
    ))
    story.append(Image(img_cwv, width=15 * cm, height=7 * cm))
    story.append(PageBreak())

    # Page 4 – Category Radar with Competitor
    story.append(Paragraph("Category Radar (with competitor overlay)", styles['H2']))
    story.append(Image(img_radar, width=12.5 * cm, height=12.5 * cm))
    story.append(PageBreak())

    # Page 5 – Top Issues & Actions
    story.append(Paragraph("Top Issues & Prioritized Actions", styles['H2']))
    story.append(Image(img_issues, width=15 * cm, height=7 * cm))
    story.append(PageBreak())

    # Page 6 – Security Posture
    story.append(Paragraph("Security & Protocol Compliance", styles['H2']))
    story.append(Image(img_sec, width=12 * cm, height=8 * cm))
    story.append(PageBreak())

    # Page 7 – Indexation & Canonicalization
    story.append(Paragraph("Indexation & Canonicalization", styles['H2']))
    robots_txt = indexation.get("robots_txt", "N/A")
    sitemap_urls = indexation.get("sitemap_urls", "N/A")
    sitemap_size_mb = indexation.get("sitemap_size_mb", "N/A")
    canonical_ok = indexation.get("canonical_ok", False)
    story.append(Paragraph(
        f"Canonical OK: {'Yes' if canonical_ok else 'No'} • robots.txt: {robots_txt} • "
        f"Sitemap: {sitemap_urls} URLs, {sitemap_size_mb} MB.",
        styles['Body']
    ))
    story.append(PageBreak())

    # Page 8 – Performance Delivery (Compression/Caching)
    story.append(Paragraph("Performance & Delivery (Compression/Caching)", styles['H2']))
    story.append(Paragraph(
        "Enable Brotli (br) for static assets with Gzip fallback; set Vary: Accept‑Encoding; "
        "precompress assets; implement Cache‑Control for static content.",
        styles['Body']
    ))
    story.append(PageBreak())

    # Page 9 – Accessibility (WCAG 2.2)
    story.append(Paragraph("Accessibility (WCAG 2.2)", styles['H2']))
    story.append(Paragraph(
        "Focus visibility, target size minimum, dragging alternatives, consistent help, "
        "accessible authentication. Improve contrast, keyboard navigation, and semantics.",
        styles['Body']
    ))
    story.append(PageBreak())

    # Page 10 – References & Roadmap
    story.append(Paragraph("References & Roadmap", styles['H2']))
    story.append(Paragraph(
        "Core Web Vitals thresholds & rationale; Lighthouse scoring weights; "
        "OWASP Secure Headers (HSTS/CSP/XFO/XCTO) and MDN; "
        "Google canonicalization, robots/meta robots, sitemap limits; "
        "WCAG 2.2 overview.",
        styles['Body']
    ))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} • {brand}", styles['Small']))

    # Build PDF
    doc.build(story)


# -------------------------- Backward‑compatible wrapper --------------------------

def render_pdf(file_path: str, brand: str, site_url: str, grade: str,
               health_score: int, category_scores, executive_summary: str):
    """
    Backward‑compatible function your existing main.py calls.
    Internally delegates to the 10‑page builder, passing minimal data plus placeholders.
    """
    render_pdf_10p(
        file_path=file_path,
        brand=brand,
        site_url=site_url,
        grade=grade,
        health_score=health_score,
        category_scores=category_scores,
        executive_summary=executive_summary,
        cwv={},                     # no CWV provided by current call
        top_issues=[],              # placeholder
        security={},                # placeholder
        indexation={},              # placeholder
        competitor=None,            # placeholder (overlay will be skipped)
        trend={"labels": ["Run"], "values": [int(health_score)]}  # simple single‑point trend
    )
``
