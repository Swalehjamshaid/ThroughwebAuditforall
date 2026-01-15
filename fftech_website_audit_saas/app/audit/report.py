import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from ..config import settings


def _chart_bar(title: str, data: dict, out_path: str, color='#2563eb'):
    plt.figure(figsize=(6,3))
    plt.bar(list(data.keys()), list(data.values()), color=color)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def _chart_pie(title: str, data: dict, out_path: str):
    plt.figure(figsize=(4,4))
    labels = list(data.keys()); values = list(data.values())
    plt.pie(values, labels=labels, autopct='%1.0f%%', startangle=140)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def _exec_summary_paragraph(url: str, score: float) -> str:
    # ~200 words high-level executive summary (deterministic)
    text = (f"This assessment provides an objective, standards-aligned evaluation of {url}, "
            f"summarizing overall technical quality, search readiness, performance posture, and growth potential. "
            f"The overall site health score is {score}%. The result is calculated from transparent category weights "
            f"covering crawlability, on-page optimization, performance signals, and mobile, security, and international hygiene. "
            f"Strengths include a stable crawl path on key pages and a foundational metadata structure on many templates. "
            f"Areas to improve typically involve normalizing titles and descriptions, tightening heading structure, and trimming render-blocking assets. "
            f"From a user-experience perspective, image optimization and consistent caching policies can lift loading speed and reduce layout shifts. "
            f"Security posture benefits from enforcing HTTPS everywhere and aligning headers with best practices. "
            f"To accelerate outcomes, start with high-impact, low-effort fixes: eliminate 4xx/5xx responses, repair internal links, and compress oversized media. "
            f"In parallel, adopt a sustainable content and internal linking plan to reinforce topical coverage and pass authority to priority URLs. "
            f"Finally, institutionalize monitoring with scheduled audits and trend reviews so improvements persist through releases. "
            f"This report includes category breakdowns, clear priorities, and export-ready artifacts for stakeholders.")
    return text


def build_pdf(audit_id: int, url: str, overall_score: float, grade: str, category_scores: dict, metrics: dict, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, f"audit_{audit_id}.pdf")

    # Charts
    chart_cat = os.path.join(out_dir, f"audit_{audit_id}_cat.png")
    _chart_bar('Category Scores', category_scores, chart_cat)
    status_dist = {'2xx': metrics.get('http_2xx',0), '3xx': metrics.get('http_3xx',0), '4xx': metrics.get('http_4xx',0), '5xx': metrics.get('http_5xx',0)}
    chart_status = os.path.join(out_dir, f"audit_{audit_id}_status.png")
    _chart_pie('HTTP Status Distribution', status_dist, chart_status)

    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    def header(page_title: str):
        try:
            c.drawImage(settings.BRAND_LOGO_PATH, 2*cm, height-3*cm, width=3*cm, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
        c.setFont('Helvetica-Bold', 16)
        c.drawString(6*cm, height-2*cm, f"{settings.BRAND_NAME} – Website Audit")
        c.setFont('Helvetica', 10)
        c.drawString(6*cm, height-2.6*cm, f"URL: {url}")
        c.drawString(6*cm, height-3.1*cm, page_title)
        c.line(2*cm, height-3.3*cm, width-2*cm, height-3.3*cm)

    def footer(conclusion: str):
        c.setFont('Helvetica-Oblique', 9)
        c.setFillColor(colors.grey)
        c.drawString(2*cm, 1.5*cm, f"Conclusion: {conclusion}")
        c.setFillColor(colors.black)
        c.drawRightString(width-2*cm, 1.5*cm, 'Certified Report – Print Ready')

    # Page 1 – Executive Summary & Grade
    header('Executive Summary & Grading')
    c.setFont('Helvetica-Bold', 28)
    c.setFillColor(colors.HexColor('#0ea5e9'))
    c.drawString(2*cm, height-5*cm, f"Overall: {overall_score}%  Grade: {grade}")
    c.setFillColor(colors.black)
    c.setFont('Helvetica', 11)
    text = c.beginText(2*cm, height-6.2*cm)
    text.setLeading(14)
    text.textLines(_exec_summary_paragraph(url, overall_score))
    c.drawText(text)
    c.drawImage(chart_cat, 2*cm, height-16*cm, width=16*cm, preserveAspectRatio=True, mask='auto')
    footer('Address quick wins first; then schedule continuous monitoring.')
    c.showPage()

    # Page 2 – Crawlability & Indexation
    header('Crawlability & Indexation')
    c.setFont('Helvetica', 11)
    c.drawString(2*cm, height-5*cm, f"Crawled: {metrics.get('total_crawled_pages',0)} pages")
    c.drawImage(chart_status, 2*cm, height-14.5*cm, width=10*cm, preserveAspectRatio=True, mask='auto')
    footer('Reduce 4xx/5xx, remove redirect chains, and fix broken links.')
    c.showPage()

    # Page 3 – On-Page SEO
    header('On-Page SEO')
    c.setFont('Helvetica', 11)
    c.drawString(2*cm, height-5*cm, f"Missing Titles: {metrics.get('missing_title',0)}  | Missing Meta: {metrics.get('missing_meta_desc',0)}  | Missing H1: {metrics.get('missing_h1',0)}")
    footer('Normalize titles, meta descriptions, and heading hierarchy per page template.')
    c.showPage()

    # Page 4 – Performance & Technical
    header('Performance & Technical')
    c.setFont('Helvetica', 11)
    c.drawString(2*cm, height-5*cm, f"Avg HTML Size: {metrics.get('total_page_size',0)} bytes  | Requests/Page: {metrics.get('requests_per_page',0)}")
    footer('Compress images, cache assets, and minimize render-blocking resources.')
    c.showPage()

    # Page 5 – Mobile, Security & Opportunities
    header('Mobile, Security & Opportunities')
    c.setFont('Helvetica', 11)
    c.drawString(2*cm, height-5*cm, 'Mobile-friendly and HTTPS baselines assumed; enable recurring audits for trends.')
    footer('Prioritize mobile CWV and security headers; plan content and internal linking growth.')
    c.showPage()

    c.save()
    return pdf_path