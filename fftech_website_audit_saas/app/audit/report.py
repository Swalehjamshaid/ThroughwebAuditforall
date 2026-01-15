
import os, textwrap
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import cm
import matplotlib.pyplot as plt
from ..config import settings


def _bar(title, data, out_path):
    plt.figure(figsize=(6,3))
    plt.bar(list(data.keys()), list(data.values()), color='#0ea5e9')
    plt.title(title)
    plt.tight_layout(); plt.savefig(out_path); plt.close()


def _summary_200_words(url: str, metrics: dict, cats: dict) -> str:
    base = f"This report provides an objective assessment of {url} using FF Tech's standardized methodology. "
    points = [
        f"We crawled {metrics.get('total_crawled_pages',0)} pages and detected status patterns including {metrics.get('http_2xx',0)} successful pages, {metrics.get('http_3xx',0)} redirects, {metrics.get('http_4xx',0)} client errors, and {metrics.get('http_5xx',0)} server errors.",
        "Crawlability is derived from error density, redirect overhead, and availability. On‑page quality reflects title and meta completeness, content accessibility, and basic structural hygiene.",
        "Performance is approximated via HTML size and request heuristics; we recommend a Lighthouse run for lab metrics and field data integration for Core Web Vitals.",
        "Category scores are weighted to reflect real‑world impact on discoverability, relevance, and user experience. The executive score summarizes these factors for leadership decisions.",
        "Immediate priorities focus on eliminating 4xx/5xx responses, providing unique titles and descriptions, compressing images, enabling caching, and minimizing render‑blocking resources.",
        "Subsequent work should target internal link equity, structured data, and mobile experience to improve long‑term stability and growth.",
    ]
    text = base + ' '.join(points)
    # pad to ~200 words
    words = text.split()
    if len(words) < 200:
        filler = (" This page‑wise analysis is intended to be actionable, transparent, and repeatable."
                  " Scores are normalized on a 0–100 scale and mapped to letter grades from A+ to D."
                  " Use scheduling for continuous monitoring and export the certified PDF for stakeholders.")
        while len(words) < 200:
            words += filler.split()
    return ' '.join(words[:210])


def build_pdf(audit_id: int, url: str, overall_score: float, grade: str, category_scores: dict, metrics: dict, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    pdf = os.path.join(out_dir, f"audit_{audit_id}.pdf")

    chart_cat = os.path.join(out_dir, f"audit_{audit_id}_cat.png")
    _bar('Category Scores', category_scores, chart_cat)
    chart_status = os.path.join(out_dir, f"audit_{audit_id}_status.png")
    _bar('HTTP Status Distribution', {
        '2xx': metrics.get('http_2xx',0), '3xx': metrics.get('http_3xx',0), '4xx': metrics.get('http_4xx',0), '5xx': metrics.get('http_5xx',0)
    }, chart_status)

    c = canvas.Canvas(pdf, pagesize=A4)
    W,H = A4

    def header(title):
        try:
            c.drawImage(settings.BRAND_LOGO_PATH, 2*cm, H-3*cm, width=3*cm, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
        c.setFont('Helvetica-Bold', 16); c.drawString(6*cm, H-2*cm, f"{settings.BRAND_NAME} – Website Audit")
        c.setFont('Helvetica', 10); c.drawString(6*cm, H-2.6*cm, f"URL: {url}"); c.drawString(6*cm, H-3.1*cm, title)
        c.line(2*cm, H-3.3*cm, W-2*cm, H-3.3*cm)

    def footer(concl):
        c.setFont('Helvetica-Oblique', 9); c.setFillColor(colors.grey)
        c.drawString(2*cm, 1.5*cm, f"Conclusion: {concl}")
        c.setFillColor(colors.black); c.drawRightString(W-2*cm, 1.5*cm, 'Certified Report')

    # Page 1 – Executive Summary
    header('Executive Summary & Grading')
    c.setFont('Helvetica-Bold', 28); c.setFillColor(colors.HexColor('#0ea5e9'))
    c.drawString(2*cm, H-5*cm, f"Overall {overall_score}%  Grade {grade}")
    c.setFillColor(colors.black); c.setFont('Helvetica', 10)
    text = c.beginText(2*cm, H-6.5*cm)
    text.setLeading(14)
    text.textLines(_summary_200_words(url, metrics, category_scores))
    c.drawText(text)
    c.drawImage(chart_cat, 2*cm, H-16*cm, width=16*cm, preserveAspectRatio=True, mask='auto')
    footer('Focus leadership attention on weak categories first.')
    c.showPage()

    # Page 2 – Crawlability & Indexation
    header('Crawlability & Indexation')
    c.setFont('Helvetica', 11)
    c.drawString(2*cm, H-5*cm, f"Crawled Pages: {metrics.get('total_crawled_pages',0)}")
    c.drawImage(chart_status, 2*cm, H-14*cm, width=16*cm, preserveAspectRatio=True, mask='auto')
    footer('Eliminate 4xx/5xx and simplify redirect paths to conserve crawl budget.')
    c.showPage()

    # Page 3 – On-Page SEO
    header('On‑Page SEO')
    c.setFont('Helvetica', 11)
    c.drawString(2*cm, H-5*cm, f"Missing Titles: {metrics.get('missing_title',0)}  Missing Meta: {metrics.get('missing_meta_desc',0)}")
    footer('Standardize titles and meta; add structured data and alt attributes.')
    c.showPage()

    # Page 4 – Performance & Technical
    header('Performance & Technical')
    c.setFont('Helvetica', 11)
    c.drawString(2*cm, H-5*cm, f"Avg HTML Size: {metrics.get('total_page_size',0)} bytes | Requests/Page: {metrics.get('requests_per_page',0)}")
    footer('Optimize images, caching, compression and reduce render‑blocking.')
    c.showPage()

    # Page 5 – Mobile, Security & Opportunities
    header('Mobile, Security & Opportunities')
    c.setFont('Helvetica', 11)
    c.drawString(2*cm, H-5*cm, 'Baseline mobile and HTTPS assumed; set up scheduled monitoring for subscribers.')
    footer('Prioritize mobile CWV, HTTPS, and quick wins; then plan long‑term upgrades.')
    c.showPage()

    c.save(); return pdf
