import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import cm
import matplotlib.pyplot as plt
from ..config import settings


def _chart_bar(title: str, data: dict, out_path: str):
    plt.figure(figsize=(6,3))
    plt.bar(list(data.keys()), list(data.values()), color='#2563eb')
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def build_pdf(audit_id: int, url: str, overall_score: float, grade: str, category_scores: dict, metrics: dict, out_dir: str, competitors: list | None = None) -> str:
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, f"audit_{audit_id}.pdf")

    chart1 = os.path.join(out_dir, f"audit_{audit_id}_cat.png")
    _chart_bar('Category Scores', category_scores, chart1)

    status_dist = {'2xx': metrics.get('http_2xx',0),'3xx': metrics.get('http_3xx',0),'4xx': metrics.get('http_4xx',0),'5xx': metrics.get('http_5xx',0)}
    chart2 = os.path.join(out_dir, f"audit_{audit_id}_status.png")
    _chart_bar('HTTP Status Distribution', status_dist, chart2)

    comp_chart = None
    if competitors:
        comp_scores = { (c.get('url','')[:18]+'…' if len(c.get('url',''))>18 else c.get('url','')): c.get('competitor_health_score',0) for c in competitors }
        comp_chart = os.path.join(out_dir, f"audit_{audit_id}_competitors.png")
        _chart_bar('Competitor Health', comp_scores, comp_chart)

    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    def header(page_title: str):
        try:
            c.drawImage(settings.BRAND_LOGO_PATH, 2*cm, height-3*cm, width=3*cm, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
        c.setFont("Helvetica-Bold", 16); c.drawString(6*cm, height-2*cm, f"{settings.BRAND_NAME} – Website Audit")
        c.setFont("Helvetica", 10); c.drawString(6*cm, height-2.6*cm, f"URL: {url}"); c.drawString(6*cm, height-3.1*cm, page_title)
        c.line(2*cm, height-3.3*cm, width-2*cm, height-3.3*cm)

    def footer(conclusion: str):
        c.setFont("Helvetica-Oblique", 9); c.setFillColor(colors.grey)
        c.drawString(2*cm, 1.5*cm, f"Conclusion: {conclusion}")
        c.setFillColor(colors.black); c.drawRightString(width-2*cm, 1.5*cm, "Certified Report – Executable Summary")

    # Page 1 – Executive Summary
    header("Executive Summary & Grading")
    c.setFont("Helvetica-Bold", 28); c.setFillColor(colors.HexColor('#0ea5e9'))
    c.drawString(2*cm, height-5*cm, f"Overall: {overall_score}%  Grade: {grade}")
    c.setFillColor(colors.black); c.setFont("Helvetica", 11)
    c.drawString(2*cm, height-6.5*cm, "Strengths: Crawlability, Content accessibility")
    c.drawString(2*cm, height-7.2*cm, "Weaknesses: Titles/Descriptions, Performance")
    c.drawImage(chart1, 2*cm, height-14*cm, width=16*cm, preserveAspectRatio=True, mask='auto')
    if comp_chart:
        c.drawImage(comp_chart, 2*cm, height-22*cm, width=16*cm, preserveAspectRatio=True, mask='auto')
    footer("Overall health is determined by weighted category scores; focus on weak areas first.")
    c.showPage()

    # Page 2 – Crawlability & Indexation
    header("Crawlability & Indexation")
    c.setFont("Helvetica", 11); c.drawString(2*cm, height-5*cm, f"Crawled Pages: {metrics.get('total_crawled_pages',0)}")
    c.drawImage(chart2, 2*cm, height-14*cm, width=16*cm, preserveAspectRatio=True, mask='auto')
    footer("Reduce 4xx/5xx and redirects; fix broken links and ensure a clean crawl path.")
    c.showPage()

    # Page 3 – On-Page SEO
    header("On-Page SEO")
    c.setFont("Helvetica", 11)
    c.drawString(2*cm, height-5*cm, f"Missing Titles: {metrics.get('missing_title',0)} | Missing Meta: {metrics.get('missing_meta_desc',0)}")
    footer("Tighten titles and descriptions; enforce one H1; add alt text and structured data.")
    c.showPage()

    # Page 4 – Performance & Technical
    header("Performance & Technical")
    c.setFont("Helvetica", 11)
    c.drawString(2*cm, height-5*cm, f"Avg HTML Size: {metrics.get('total_page_size',0)} bytes | Requests/Page: {metrics.get('requests_per_page',0)}")
    footer("Improve LCP/CLS via image optimization, caching, and reducing render-blocking.")
    c.showPage()

    # Page 5 – Mobile, Security & Opportunities
    header("Mobile, Security & Opportunities")
    c.setFont("Helvetica", 11); c.drawString(2*cm, height-5*cm, "Mobile-friendly and HTTPS baseline assumed; set up monitoring and quick wins.")
    footer("Prioritize mobile CWV, HTTPS, and quick fixes; then plan long-term upgrades.")
    c.showPage()

    c.save(); return pdf_path