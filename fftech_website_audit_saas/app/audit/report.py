import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import cm
import matplotlib.pyplot as plt

BRAND_LOGO_PATH = os.getenv('BRAND_LOGO_PATH', 'app/static/img/logo.png')
BRAND = os.getenv('BRAND_NAME', 'FF Tech')


def _chart_bar(title: str, data: dict, out_path: str, color: str = '#2563eb'):
    plt.figure(figsize=(6,3))
    plt.bar(list(data.keys()), list(data.values()), color=color)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def build_pdf(doc_id: str, url: str, overall_score: float, grade: str, category_scores: dict, metrics: dict, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, f"audit_{doc_id}.pdf")

    chart1 = os.path.join(out_dir, f"audit_{doc_id}_cat.png")
    _chart_bar('Category Scores', category_scores, chart1)

    status = {
        '2xx': metrics.get('http_2xx',0),
        '3xx': metrics.get('http_3xx',0),
        '4xx': metrics.get('http_4xx',0),
        '5xx': metrics.get('http_5xx',0),
    }
    chart2 = os.path.join(out_dir, f"audit_{doc_id}_status.png")
    _chart_bar('HTTP Status Distribution', status, chart2, color='#10b981')

    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    def header(page_title: str):
        try:
            c.drawImage(BRAND_LOGO_PATH, 2*cm, height-3*cm, width=3*cm, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
        c.setFont("Helvetica-Bold", 16)
        c.drawString(6*cm, height-2*cm, f"{BRAND} – Website Audit")
        c.setFont("Helvetica", 10)
        c.drawString(6*cm, height-2.6*cm, f"URL: {url}")
        c.drawString(6*cm, height-3.1*cm, page_title)
        c.line(2*cm, height-3.3*cm, width-2*cm, height-3.3*cm)

    def footer(conclusion: str):
        c.setFont("Helvetica-Oblique", 9)
        c.setFillColor(colors.grey)
        c.drawString(2*cm, 1.5*cm, f"Conclusion: {conclusion}")
        c.setFillColor(colors.black)
        c.drawRightString(width-2*cm, 1.5*cm, "Certified Report – Executive Ready")

    # Page 1 – Executive Summary
    header("Executive Summary & Grading")
    c.setFont("Helvetica-Bold", 28)
    c.setFillColor(colors.HexColor('#0ea5e9'))
    c.drawString(2*cm, height-5*cm, f"Overall: {overall_score}%  Grade: {grade}")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 11)
    c.drawString(2*cm, height-6.5*cm, "Strengths: Crawlability, Content accessibility")
    c.drawString(2*cm, height-7.2*cm, "Weaknesses: Titles/Descriptions, Performance")
    c.drawImage(chart1, 2*cm, height-14*cm, width=16*cm, preserveAspectRatio=True, mask='auto')
    footer("Weighted categories produce the health score. Address weak areas first.")
    c.showPage()

    # Page 2 – Crawlability & Indexation
    header("Crawlability & Indexation")
    c.setFont("Helvetica", 11)
    c.drawString(2*cm, height-5*cm, f"Pages Crawled: {metrics.get('total_crawled_pages',0)}")
    c.drawImage(chart2, 2*cm, height-14*cm, width=16*cm, preserveAspectRatio=True, mask='auto')
    footer("Reduce 4xx/5xx and long redirect chains; keep sitemaps and canonicals clean.")
    c.showPage()

    # Page 3 – On-Page SEO
    header("On-Page SEO")
    c.setFont("Helvetica", 11)
    c.drawString(2*cm, height-5*cm, f"Missing Titles: {metrics.get('missing_title',0)}  |  Missing Meta: {metrics.get('missing_meta_desc',0)}")
    footer("Ensure one H1, concise titles & metas, alt text, and structured data.")
    c.showPage()

    # Page 4 – Performance & Technical
    header("Performance & Technical")
    c.setFont("Helvetica", 11)
    c.drawString(2*cm, height-5*cm, f"Avg HTML size: {metrics.get('total_page_size',0)} bytes  |  Requests/Page (est.): {metrics.get('requests_per_page',0)}")
    footer("Improve LCP, CLS, TBT with image optimization, caching, and fewer render blockers.")
    c.showPage()

    # Page 5 – Mobile, Security & Opportunities
    header("Mobile, Security & Opportunities")
    c.setFont("Helvetica", 11)
    c.drawString(2*cm, height-5*cm, "Mobile-friendly & HTTPS baseline assumed. Set monitoring & quick wins.")
    footer("Prioritize mobile CWV, HTTPS, quick wins; then plan long-term enhancements.")
    c.showPage()

    c.save()
    return pdf_path