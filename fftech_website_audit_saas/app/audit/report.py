
# app/audit/report.py
# -*- coding: utf-8 -*-
"""
FF Tech – Executive Website Audit v3 (10 pages, comprehensive)
Generates an executive-grade PDF with full metrics and competitor analysis.

Dependencies: reportlab, matplotlib, numpy (bundled in your environment).
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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table, TableStyle


# -------------------------- Chart helpers --------------------------

def _save_gauge(score: int, path: str, title: str = "Overall Health"):
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.set_aspect('equal')
    s = max(0, min(100, int(score)))
    wedges = [s, 100 - s]
    ax.pie(
        wedges,
        colors=['#10B981', '#EEEEEE'],
        startangle=90,
        counterclock=False,
        wedgeprops=dict(width=0.35, edgecolor='white')
    )
    ax.text(0, 0.02, f"{s}", ha='center', va='center', fontsize=20, fontweight='bold', color='#333')
    ax.text(0, -0.25, title, ha='center', va='center', fontsize=10, color='#666')
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches='tight')
    plt.close(fig)


def _save_cwv_micro(cwv: dict, path: str):
    LCP = float(cwv.get('LCP', 0))     # seconds
    INP = float(cwv.get('INP', 0))     # ms
    CLS = float(cwv.get('CLS', 0))     # unitless
    TBT = float(cwv.get('TBT', 0))     # ms (lab proxy)

    metrics = ['LCP (s)', 'INP (ms)', 'CLS', 'TBT (ms)']
    values = [LCP, INP, CLS, TBT]

    fig, ax = plt.subplots(figsize=(6, 3))
    ax.bar(metrics, values, color=['#10B981'] * 4)

    # Threshold lines (Google guidance)
    ax.axhline(2.5, color='#F59E0B', lw=1, ls='--'); ax.text(-0.4, 2.5, 'LCP ≤2.5s', fontsize=8, color='#F59E0B')
    ax.axhline(200, color='#F59E0B', lw=1, ls='--'); ax.text(0.8, 200, 'INP ≤200ms', fontsize=8, color='#F59E0B')
    ax.axhline(0.1, color='#F59E0B', lw=1, ls='--'); ax.text(1.8, 0.1, 'CLS ≤0.1', fontsize=8, color='#F59E0B')
    ax.axhline(200, color='#F59E0B', lw=1, ls='--'); ax.text(2.8, 200, 'TBT ≤200ms', fontsize=8, color='#F59E0B')
    ax.set_ylabel('Value')
    ax.set_title('Core Web Vitals (thresholds)')
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches='tight')
    plt.close(fig)


def _save_radar(labels, values, labels2, values2, path: str):
    labels = list(labels or [])
    values = list(values or [])
    N = len(labels) if labels else 5
    if not labels:
        labels = ["Performance", "Accessibility", "SEO", "Security", "BestPractices"]
        values = [0, 0, 0, 0, 0]

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
        labels, values = ["No issues detected"], [0]
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.barh(labels, values, color='#F59E0B')
    ax.invert_yaxis()
    ax.set_xlabel('Frequency')
    ax.set_title('Top Issues (counts)')
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches='tight')
    plt.close(fig)


def _save_security_heatmap(sec_dict: dict, path: str):
    keys = ["HSTS", "CSP", "XFO", "XCTO", "SSL_Valid", "MixedContent"]
    vals = [sec_dict.get(k, None) for k in keys]

    def to_score(v):
        if isinstance(v, bool): return 1 if v else 0
        if isinstance(v, str):
            v_lower = v.lower()
            if v_lower in ("yes", "enabled", "valid", "pass"): return 1
            if v_lower in ("no", "disabled", "fail"): return 0
        return 0

    grid = np.array([to_score(v) for v in vals]).reshape(2, 3)

    fig, ax = plt.subplots(figsize=(5, 3.2))
    cmap = mcolors.ListedColormap(['#EF4444', '#10B981'])
    ax.imshow(grid, cmap=cmap, vmin=0, vmax=1)
    ax.set_xticks([0, 1, 2]); ax.set_yticks([0, 1])
    ax.set_xticklabels(keys[0:3]); ax.set_yticklabels(["", ""])
    for i in range(2):
        for j in range(3):
            label = keys[i*3+j]
            val = 'Pass' if grid[i,j]==1 else 'Fail'
            ax.text(j, i, f"{label}\n{val}", ha='center', va='center', color='white', fontsize=8)
    ax.set_title('Security & Protocol Compliance')
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches='tight')
    plt.close(fig)


def _save_trend_line(labels, values, path: str):
    labels = list(labels or []); values = list(values or [])
    if not labels or not values: labels, values = ["Run 1"], [0]
    fig, ax = plt.subplots(figsize=(5.2, 3.2))
    ax.plot(labels, values, marker='o', color='#10B981')
    ax.set_ylim(0, 100); ax.set_ylabel('Health'); ax.set_title('Recent Health Trend')
    plt.grid(alpha=0.2); plt.tight_layout(); plt.savefig(path, dpi=180, bbox_inches='tight'); plt.close(fig)


# -------------------------- Table helper --------------------------

def _kv_table(data_left: dict, data_right: dict | None = None, col_labels=("Metric", "Value", "Competitor")):
    """
    Build a two/three-column table from dictionaries.
    data_left: dict of site metrics
    data_right: dict of competitor metrics (optional)
    """
    rows = [[col_labels[0], col_labels[1], col_labels[2]]] if data_right else [[col_labels[0], col_labels[1]]]
    for k, v in (data_left or {}).items():
        if data_right:
            rows.append([str(k), str(v), str(data_right.get(k, "—"))])
        else:
            rows.append([str(k), str(v)])
    table = Table(rows, hAlign='LEFT')
    style = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#12172B')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#2c324a')),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#0E1326')),
        ('TEXTCOLOR', (0,1), (-1,-1), colors.HexColor('#E5E7EB')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#0E1326'), colors.HexColor('#111726')]),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ])
    table.setStyle(style)
    return table


# -------------------------- 10‑page PDF builder --------------------------

def render_pdf_10p(
    file_path: str,
    brand: str,
    site_url: str,
    grade: str,
    health_score: int,
    category_scores,
    executive_summary: str = "",
    # Detailed sections
    cwv: dict | None = None,               # {"LCP":s,"INP":ms,"CLS":x,"TBT":ms}
    performance: dict | None = None,       # perf lab: FCP, Speed Index, TTI, TTFB, Page size, Requests, Long tasks, etc.
    seo: dict | None = None,               # title length, meta description length, H1 count, images alt missing, structured data, canonical presence...
    security: dict | None = None,          # HSTS, CSP, XFO, XCTO, SSL valid/expired, mixed content count...
    indexation: dict | None = None,        # canonical_ok, robots_txt summary, sitemap URLs/size, hreflang, pagination...
    accessibility: dict | None = None,     # WCAG 2.2 checks: focus, target size, drag alt, contrast, aria, labels...
    delivery: dict | None = None,          # Compression, Cache-Control, Vary, CDN, precompression...
    mobile: dict | None = None,            # viewport meta, mobile-friendly flags, touch target size, etc.
    top_issues: list | None = None,        # [(issue, count), ...]
    competitor: dict | None = None,        # {"url":str, sections: same keys as above}
    trend: dict | None = None              # {"labels":[...], "values":[...]}
):
    """
    Build a 10‑page executive PDF with charts, tables, and competitor overlay across all sections.
    """

    # Prepare images dir
    img_dir = os.path.join("/tmp", "audit_imgs")
    os.makedirs(img_dir, exist_ok=True)

    # Normalize categories to list of (name, score)
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

    comp_url = None
    comp_labels, comp_values = None, None
    comp_sections = {}

    if competitor and isinstance(competitor, dict):
        comp_url = competitor.get("url")
        comp_pairs = to_pairs(competitor.get("category_scores", []))
        if comp_pairs:
            comp_labels = [n for n, _ in comp_pairs]
            comp_values = [s for _, s in comp_pairs]
        # section dicts
        for k in ["cwv","performance","seo","security","indexation","accessibility","delivery","mobile"]:
            comp_sections[k] = competitor.get(k, {}) if isinstance(competitor.get(k, {}), dict) else {}

    # Defaults
    cwv = cwv or {}
    performance = performance or {}
    seo = seo or {}
    security = security or {}
    indexation = indexation or {}
    accessibility = accessibility or {}
    delivery = delivery or {}
    mobile = mobile or {}
    top_issues = top_issues or []
    trend = trend or {"labels": [], "values": []}

    # Generate charts
    img_gauge = os.path.join(img_dir, 'gauge.png');    _save_gauge(health_score, img_gauge)
    img_cwv   = os.path.join(img_dir, 'cwv.png');      _save_cwv_micro(cwv, img_cwv)
    img_radar = os.path.join(img_dir, 'radar.png');    _save_radar(labels, values, comp_labels, comp_values, img_radar)
    img_issues= os.path.join(img_dir, 'issues.png');   _save_issues_bar(top_issues, img_issues)
    img_sec   = os.path.join(img_dir, 'security.png'); _save_security_heatmap(security, img_sec)
    img_trend = os.path.join(img_dir, 'trend.png');    _save_trend_line(trend.get("labels", []), trend.get("values", []), img_trend)

    # PDF styles
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='H1', fontSize=18, leading=22, spaceAfter=12, textColor=colors.HexColor('#4F46E5')))
    styles.add(ParagraphStyle(name='H2', fontSize=14, leading=18, spaceAfter=8, textColor=colors.HexColor('#10B981')))
    styles.add(ParagraphStyle(name='Body', fontSize=10, leading=14, spaceAfter=6))
    styles.add(ParagraphStyle(name='Small', fontSize=8, leading=12, textColor=colors.grey))

    story = []
    doc = SimpleDocTemplate(file_path, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm)

    # Page 1 – Cover & Executive Overview + Trend
    story.append(Paragraph(f"{brand} – Executive Website Audit (v3, 10 pages)", styles['H1']))
    story.append(Paragraph(f"Site: {site_url}", styles['Body']))
    if comp_url: story.append(Paragraph(f"Competitor: {comp_url}", styles['Body']))
    story.append(Spacer(1, 6)); story.append(Paragraph("Executive Overview", styles['H2']))
    story.append(Paragraph(executive_summary or "This report summarizes technical health, CWV, security, indexation, SEO, accessibility, delivery, mobile readiness, and competitive positioning.", styles['Body']))
    story.append(Spacer(1, 10)); story.append(Image(img_trend, width=12 * cm, height=7 * cm))
    story.append(Paragraph("Trend: Health scores across recent audits.", styles['Small'])); story.append(PageBreak())

    # Page 2 – KPI & Gauge + Category quick table
    story.append(Paragraph("KPIs & Overall Health Gauge", styles['H2']))
    story.append(Paragraph(f"Grade: {grade} • Overall Health: {int(health_score)}/100.", styles['Body']))
    story.append(Image(img_gauge, width=10 * cm, height=10 * cm))
    # quick category table
    story.append(Spacer(1, 8))
    cat_table_data = {n: s for n, s in zip(labels, values)}
    comp_cat_table_data = {n: s for n, s in zip(comp_labels or [], comp_values or [])}
    story.append(_kv_table(cat_table_data, comp_cat_table_data))
    story.append(PageBreak())

    # Page 3 – Core Web Vitals (chart + table)
    story.append(Paragraph("Core Web Vitals (CWV)", styles['H2']))
    story.append(Image(img_cwv, width=15 * cm, height=7 * cm))
    story.append(Spacer(1, 6))
    cwv_table_left = {
        "LCP (s)": cwv.get("LCP", "—"),
        "INP (ms)": cwv.get("INP", "—"),
        "CLS": cwv.get("CLS", "—"),
        "TBT (ms)": cwv.get("TBT", "—"),
    }
    story.append(_kv_table(cwv_table_left, {
        "LCP (s)": comp_sections["cwv"].get("LCP", "—"),
        "INP (ms)": comp_sections["cwv"].get("INP", "—"),
        "CLS": comp_sections["cwv"].get("CLS", "—"),
        "TBT (ms)": comp_sections["cwv"].get("TBT", "—"),
    } if comp_url else None))
    story.append(PageBreak())

    # Page 4 – Category Radar with Competitor + Performance lab table
    story.append(Paragraph("Category Radar (Competitor overlay)", styles['H2']))
    story.append(Image(img_radar, width=12.5 * cm, height=12.5 * cm))
    story.append(Spacer(1, 6))
    perf_table_left = {
        "FCP (s)": performance.get("FCP", "—"),
        "Speed Index": performance.get("SpeedIndex", "—"),
        "TTI (s)": performance.get("TTI", "—"),
        "TTFB (ms)": performance.get("TTFB", "—"),
        "Page size (MB)": performance.get("TotalPageSizeMB", "—"),
        "Requests/page": performance.get("RequestsPerPage", "—"),
        "Long tasks (count)": performance.get("LongTasks", "—"),
        "Render-blocking resources": performance.get("RenderBlocking", "—"),
    }
    perf_comp = {
        "FCP (s)": comp_sections["performance"].get("FCP", "—"),
        "Speed Index": comp_sections["performance"].get("SpeedIndex", "—"),
        "TTI (s)": comp_sections["performance"].get("TTI", "—"),
        "TTFB (ms)": comp_sections["performance"].get("TTFB", "—"),
        "Page size (MB)": comp_sections["performance"].get("TotalPageSizeMB", "—"),
        "Requests/page": comp_sections["performance"].get("RequestsPerPage", "—"),
        "Long tasks (count)": comp_sections["performance"].get("LongTasks", "—"),
        "Render-blocking resources": comp_sections["performance"].get("RenderBlocking", "—"),
    } if comp_url else None
    story.append(_kv_table(perf_table_left, perf_comp))
    story.append(PageBreak())

    # Page 5 – Top Issues (bar) + SEO table
    story.append(Paragraph("Top Issues & SEO Diagnostics", styles['H2']))
    story.append(Image(img_issues, width=15 * cm, height=7 * cm))
    story.append(Spacer(1, 6))
    seo_table_left = {
        "Title length": seo.get("TitleLength", "—"),
        "Meta desc length": seo.get("MetaDescriptionLength", "—"),
        "H1 count": seo.get("H1Count", "—"),
        "Images without alt": seo.get("ImagesWithoutAlt", "—"),
        "Structured data": seo.get("StructuredData", "—"),
        "Canonical present": seo.get("CanonicalPresent", "—"),
        "Open Graph/Twitter": seo.get("SocialMeta", "—"),
        "Duplicate titles": seo.get("DuplicateTitles", "—"),
    }
    seo_comp = {k: comp_sections["seo"].get(k, "—") for k in seo_table_left} if comp_url else None
    story.append(_kv_table(seo_table_left, seo_comp))
    story.append(PageBreak())

    # Page 6 – Security posture (heatmap) + headers table
    story.append(Paragraph("Security & Protocol Compliance", styles['H2']))
    story.append(Image(img_sec, width=12 * cm, height=8 * cm))
    story.append(Spacer(1, 6))
    sec_table_left = {
        "HTTPS": security.get("HTTPS", "—"),
        "HSTS (RFC 6797)": security.get("HSTS", "—"),
        "CSP": security.get("CSP", "—"),
        "X-Frame-Options": security.get("XFO", "—"),
        "X-Content-Type-Options": security.get("XCTO", "—"),
        "Referrer-Policy": security.get("ReferrerPolicy", "—"),
        "SSL valid": security.get("SSL_Valid", "—"),
        "Mixed content": security.get("MixedContentCount", "—")
    }
    sec_comp = {k: comp_sections["security"].get(k, "—") for k in sec_table_left} if comp_url else None
    story.append(_kv_table(sec_table_left, sec_comp))
    story.append(PageBreak())

    # Page 7 – Indexation & Canonicalization + Sitemaps table
    story.append(Paragraph("Indexation & Canonicalization", styles['H2']))
    idx_table_left = {
        "Canonical OK": "Yes" if indexation.get("CanonicalOK") else "No",
        "robots.txt summary": indexation.get("RobotsTxt", "—"),
        "Meta robots": indexation.get("MetaRobots", "—"),
        "Sitemap URLs": indexation.get("SitemapURLs", "—"),
        "Sitemap size (MB)": indexation.get("SitemapSizeMB", "—"),
        "Hreflang": indexation.get("Hreflang", "—"),
        "Pagination": indexation.get("Pagination", "—")
    }
    idx_comp = {k: comp_sections["indexation"].get(k, "—") for k in idx_table_left} if comp_url else None
    story.append(_kv_table(idx_table_left, idx_comp))
    story.append(PageBreak())

    # Page 8 – Delivery (Compression/Caching/CDN) table
    story.append(Paragraph("Performance Delivery (Compression/Caching/CDN)", styles['H2']))
    deliv_table_left = {
        "Content-Encoding": delivery.get("ContentEncoding", "—"),
        "Vary: Accept-Encoding": delivery.get("VaryAE", "—"),
        "Cache-Control": delivery.get("CacheControl", "—"),
        "ETag": delivery.get("ETag", "—"),
        "CDN": delivery.get("CDN", "—"),
        "Precompressed assets (.br/.gz)": delivery.get("Precompressed", "—")
    }
    deliv_comp = {k: comp_sections["delivery"].get(k, "—") for k in deliv_table_left} if comp_url else None
    story.append(_kv_table(deliv_table_left, deliv_comp))
    story.append(PageBreak())

    # Page 9 – Accessibility (WCAG 2.2) table + Mobile readiness
    story.append(Paragraph("Accessibility (WCAG 2.2)", styles['H2']))
    acc_table_left = {
        "Focus not obscured": accessibility.get("FocusNotObscured", "—"),
        "Focus appearance": accessibility.get("FocusAppearance", "—"),
        "Target size min": accessibility.get("TargetSize", "—"),
        "Dragging alt": accessibility.get("DraggingAlt", "—"),
        "Consistent help": accessibility.get("ConsistentHelp", "—"),
        "Accessible auth": accessibility.get("AccessibleAuth", "—"),
        "Contrast failures": accessibility.get("ContrastFails", "—"),
        "ARIA/labels": accessibility.get("AriaLabels", "—"),
    }
    acc_comp = {k: comp_sections["accessibility"].get(k, "—") for k in acc_table_left} if comp_url else None
    story.append(_kv_table(acc_table_left, acc_comp))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Mobile Readiness", styles['H2']))
    mob_table_left = {
        "Viewport meta": mobile.get("ViewportMeta", "—"),
        "Mobile friendly": mobile.get("MobileFriendly", "—"),
        "Tap target size": mobile.get("TapTargetSize", "—"),
        "Responsive images": mobile.get("ResponsiveImages", "—")
    }
    mob_comp = {k: comp_sections["mobile"].get(k, "—") for k in mob_table_left} if comp_url else None
    story.append(_kv_table(mob_table_left, mob_comp))
    story.append(PageBreak())

    # Page 10 – References & Roadmap
    story.append(Paragraph("References & Roadmap", styles['H2']))
    story.append(Paragraph(
        "Core Web Vitals thresholds & 75th percentile classification; Lighthouse scoring weights; "
        "OWASP Secure Headers (HSTS/CSP/XFO/XCTO) and MDN; "
        "Google canonicalization, robots/meta robots, sitemap size limits; WCAG 2.2 updates.",
        styles['Body']
    ))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} • {brand}",
        styles['Small']
    ))

    doc.build(story)


# -------------------------- Backward‑compatible wrapper --------------------------

def render_pdf(file_path: str, brand: str, site_url: str, grade: str,
               health_score: int, category_scores, executive_summary: str):
    """
    Legacy wrapper used by current main.py routes — now builds the 10‑page report with minimal data.
    For full fidelity, switch routes to call render_pdf_10p(...) and pass all sections.
    """
    render_pdf_10p(
        file_path=file_path,
        brand=brand,
        site_url=site_url,
        grade=grade,
        health_score=health_score,
        category_scores=category_scores,
        executive_summary=executive_summary,
        # Empty sections defaulted; will render placeholders
        cwv={}, performance={}, seo={}, security={}, indexation={}, accessibility={}, delivery={}, mobile={},
        top_issues=[], competitor=None,
        trend={"labels": ["Run"], "values": [int(health_score)]}
    )
