import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import matplotlib.pyplot as plt

BRAND_NAME = os.getenv('BRAND_NAME', 'FF Tech')
BRAND_LOGO_PATH = os.getenv('BRAND_LOGO_PATH', 'app/static/img/logo.png')


def _chart_bar(title: str, data: dict, out_path: str, color='#2563eb'):
    plt.figure(figsize=(6,3))
    plt.bar(list(data.keys()), list(data.values()), color=color)
    plt.title(title)
    plt.xticks(rotation=25, ha='right')
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def _chart_pie(title: str, data: dict, out_path: str):
    plt.figure(figsize=(4.5,4.5))
    labels = list(data.keys()); sizes = list(data.values())
    if sum(sizes) == 0: sizes = [1]*len(sizes)
    plt.pie(sizes, labels=labels, autopct='%1.0f%%', startangle=140)
    plt.title(title)
    plt.tight_layout(); plt.savefig(out_path); plt.close()


def _paragraph(c, text: str, x: float, y: float, width: float, leading=14):
    # simple paragraph wrapper
    from textwrap import wrap
    c.setFont('Helvetica', 10)
    y_cursor = y
    for line in wrap(text, width=int(width/4)):
        c.drawString(x, y_cursor, line)
        y_cursor -= leading


def generate_exec_summary(url: str, category_scores: dict, metrics: dict) -> str:
    # ~200 words narrative
    focus = []
    if metrics.get('http_4xx',0) or metrics.get('http_5xx',0):
        focus.append('resolve client and server errors to stabilize crawlability')
    if metrics.get('missing_title',0) or metrics.get('missing_meta_desc',0):
        focus.append('standardize titles and meta descriptions to strengthen relevance and CTR')
    if metrics.get('total_page_size',0) > 200000:
        focus.append('optimize images and trim render-blocking resources to improve loading')
    if not focus:
        focus.append('maintain ongoing monitoring and strengthen internal linking and structured data')
    txt = (
        f"This automated audit provides a concise, executive view of {url}. The overall score reflects a weighted "
        f"blend of crawlability, on-page optimization, performance, and mobile/security signals. The crawl surfaced "
        f"{metrics.get('total_crawled_pages',0)} HTML pages with status distribution across 2xx, 3xx, 4xx, and 5xx. "
        f"Category leaders include areas with consistent accessibility and markup hygiene, while opportunities center on "
        f"removing friction that impacts discovery, rendering, and user engagement. Based on observed patterns, the top "
        f"priorities are to {', and '.join(focus)}. Addressing these items typically improves Core Web Vitals proxies, "
        f"reduces wasted crawl budget, and increases the likelihood of richer search presentation. The remaining actions "
        f"include validating canonicalization and social metadata, auditing orphan pages, and establishing a sustainable "
        f"governance routine. The metrics and charts that follow are organized to highlight immediate fixes, medium-term "
        f"enhancements, and strategic growth levers. Once the critical items are remediated, consider enabling scheduled "
        f"audits for continuous assurance and benchmarking versus competitors."
    )
    return txt


def build_pdf(audit_id: int, url: str, overall_score: float, grade: str, category_scores: dict, metrics: dict, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, f"audit_{audit_id}.pdf")

    chart1 = os.path.join(out_dir, f"audit_{audit_id}_cats.png")
    _chart_bar('Category Scores', category_scores, chart1)

    status = {'2xx': metrics.get('http_2xx',0), '3xx': metrics.get('http_3xx',0), '4xx': metrics.get('http_4xx',0), '5xx': metrics.get('http_5xx',0)}
    chart2 = os.path.join(out_dir, f"audit_{audit_id}_status.png")
    _chart_pie('HTTP Status Distribution', status, chart2)

    sev = {'Risk': metrics.get('risk_severity_index',0), 'Opportunity': category_scores.get('opportunities',0)}
    chart3 = os.path.join(out_dir, f"audit_{audit_id}_severity.png")
    _chart_bar('Severity & Opportunity', sev, chart3, color='#ef4444')

    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    def header(page_title: str):
        try:
            c.drawImage(BRAND_LOGO_PATH, 2*cm, height-3*cm, width=3*cm, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
        c.setFont('Helvetica-Bold', 16)
        c.drawString(6*cm, height-2*cm, f"{BRAND_NAME} – Website Audit")
        c.setFont('Helvetica', 10)
        c.drawString(6*cm, height-2.6*cm, f"URL: {url}")
        c.drawString(6*cm, height-3.1*cm, page_title)
        c.line(2*cm, height-3.3*cm, width-2*cm, height-3.3*cm)

    def footer(conclusion: str):
        c.setFont('Helvetica-Oblique', 9)
        c.setFillColor(colors.grey)
        c.drawString(2*cm, 1.5*cm, f"Conclusion: {conclusion}")
        c.setFillColor(colors.black)
        c.drawRightString(width-2*cm, 1.5*cm, 'Certified – Print Ready')

    # Page 1: Executive Summary & Grade
    header('Executive Summary & Grading')
    c.setFont('Helvetica-Bold', 28)
    c.setFillColor(colors.HexColor('#0ea5e9'))
    c.drawString(2*cm, height-5*cm, f"Overall: {overall_score}%  Grade: {grade}")
    c.setFillColor(colors.black)
    c.drawImage(chart1, 2*cm, height-14*cm, width=16*cm, preserveAspectRatio=True, mask='auto')
    _paragraph(c, generate_exec_summary(url, category_scores, metrics), 2*cm, height-15*cm, width-4*cm)
    footer('Focus critical fixes in the next sprint; schedule follow-up audit in 14 days.')
    c.showPage()

    # Page 2: Crawlability & Indexation
    header('Crawlability & Indexation')
    c.setFont('Helvetica', 11)
    c.drawString(2*cm, height-5*cm, f"Crawled: {metrics.get('total_crawled_pages',0)} | 4xx: {metrics.get('http_4xx',0)} | 5xx: {metrics.get('http_5xx',0)}")
    c.drawImage(chart2, 2*cm, height-13*cm, width=10*cm, preserveAspectRatio=True, mask='auto')
    footer('Eliminate 4xx/5xx; simplify redirects; verify robots and sitemaps for coverage.')
    c.showPage()

    # Page 3: On-Page SEO
    header('On-Page SEO')
    c.setFont('Helvetica', 11)
    c.drawString(2*cm, height-5*cm, f"Missing Titles: {metrics.get('missing_title',0)} | Missing Meta: {metrics.get('missing_meta_desc',0)} | Broken Anchors: {metrics.get('broken_anchor_links',0)}")
    footer('Standardize titles, meta, H1s, alt attributes; align URLs and canonical tags.')
    c.showPage()

    # Page 4: Performance & Technical
    header('Performance & Technical')
    c.setFont('Helvetica', 11)
    c.drawString(2*cm, height-5*cm, f"Avg HTML Size: {metrics.get('total_page_size',0)} bytes | Requests/Page: {metrics.get('requests_per_page',0)}")
    c.drawImage(chart3, 2*cm, height-13*cm, width=12*cm, preserveAspectRatio=True, mask='auto')
    footer('Optimize images, caching, and render-blocking resources to lift LCP and TBT proxies.')
    c.showPage()

    # Page 5: Mobile, Security & Opportunities
    header('Mobile, Security & Opportunities')
    c.setFont('Helvetica', 11)
    c.drawString(2*cm, height-5*cm, 'Baseline mobile-friendly and HTTPS assumed; add structured data and tracking governance.')
    footer('Enable scheduled reporting to sustain improvements and benchmark vs. competitors.')
    c.showPage()

    c.save()
    return pdf_path