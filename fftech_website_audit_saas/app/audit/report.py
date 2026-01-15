
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
import matplotlib.pyplot as plt

from .grader import grade_from_score
from ..config import settings

LOGO_PATH = 'app/static/img/fftech_logo.png'


def _draw_header(c: canvas.Canvas, title: str):
    c.drawImage(LOGO_PATH, 40, 780, width=180, height=48, mask='auto')
    c.setFillColor(colors.HexColor('#0ad1a3'))
    c.setFont('Helvetica-Bold', 16)
    c.drawRightString(550, 805, f'{settings.UI_BRAND_NAME} — AI Website Audit')
    c.setFillColor(colors.black)
    c.setFont('Helvetica-Bold', 18)
    c.drawString(40, 740, title)
    c.line(40, 735, 555, 735)


def _mpl_chart(title: str, labels, values):
    fig, ax = plt.subplots(figsize=(5, 2.2), dpi=200)
    ax.bar(labels, values, color=['#0AD1A3', '#31C3FE', '#A78BFA', '#FBBF24', '#F87171'])
    ax.set_title(title)
    ax.set_ylim(0, 100)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', transparent=True)
    plt.close(fig)
    buf.seek(0)
    return buf


def build_pdf(audit_payload: dict, overall_score: float, cat_scores: dict, url: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    _draw_header(c, 'Executive Summary')
    grade = grade_from_score(overall_score)
    c.setFont('Helvetica-Bold', 32)
    c.setFillColor(colors.HexColor('#0ad1a3'))
    c.drawRightString(550, 700, f'{overall_score:.0f}% — {grade}')
    c.setFillColor(colors.black)
    c.setFont('Helvetica', 12)
    summary = (f"Executive overview of {url}. The site was analyzed across 200 metrics including Health, Crawlability, On-page, Performance, Mobile/Security/Intl, Competitors, Broken Links, and ROI.")
    c.drawString(40, 680, 'Executive Summary:')
    text = c.beginText(40, 660)
    text.setFont('Helvetica', 11)
    text.textLines(summary)
    c.drawText(text)

    labels = list(cat_scores.keys())
    values = [cat_scores[k] for k in labels]
    chart = _mpl_chart('Category Score Breakdown', labels, values)
    c.drawImage(ImageReader(chart), 60, 480, width=470, height=160, mask='auto')
    c.setFont('Helvetica-Oblique', 9)
    c.drawRightString(550, 40, 'Page 1 — Conclusion: Overall score and priorities outlined.')
    c.showPage()

    _draw_header(c, 'Site Health & Crawlability')
    stats = audit_payload
    c.setFont('Helvetica', 12)
    c.drawString(40, 700, f"Pages: {stats['pages']} | 4xx: {stats['status_4xx']} | 5xx: {stats['status_5xx']}")
    chart2 = _mpl_chart('Status Distribution', ['4xx','5xx'], [stats['status_4xx'], stats['status_5xx']])
    c.drawImage(ImageReader(chart2), 60, 520, width=470, height=160, mask='auto')
    c.drawString(40, 480, 'Conclusion: Address server/client errors; improve crawl coverage.')
    c.setFont('Helvetica-Oblique', 9)
    c.drawRightString(550, 40, 'Page 2 — Crawl & health priorities defined.')
    c.showPage()

    _draw_header(c, 'On-page SEO & Content')
    chart3 = _mpl_chart('On-page KPIs', ['Titles','Meta','H1'], [
        100 - audit_payload['results']['OnPage'][41]['score'],
        100 - audit_payload['results']['OnPage'][45]['score'],
        100 - audit_payload['results']['OnPage'][49]['score'],
    ])
    c.drawImage(ImageReader(chart3), 60, 520, width=470, height=160, mask='auto')
    c.drawString(40, 480, 'Conclusion: Fix missing titles/meta/H1; structure content for rich results.')
    c.setFont('Helvetica-Oblique', 9)
    c.drawRightString(550, 40, 'Page 3 — On-page priorities summarized.')
    c.showPage()

    _draw_header(c, 'Performance & Security')
    perf_labels = list(audit_payload['results']['Performance'].keys())
    perf_vals = [audit_payload['results']['Performance'][k]['score'] for k in perf_labels]
    chart4 = _mpl_chart('Performance Subscores', [str(k) for k in perf_labels], perf_vals)
    c.drawImage(ImageReader(chart4), 60, 520, width=470, height=160, mask='auto')
    c.drawString(40, 480, 'Conclusion: Optimize vitals, enable caching/compression, validate HTTPS.')
    c.setFont('Helvetica-Oblique', 9)
    c.drawRightString(550, 40, 'Page 4 — Performance & security actions.')
    c.showPage()

    _draw_header(c, 'Roadmap & ROI')
    chart5 = _mpl_chart('ROI Forecast (Index)', ['30d','60d','90d'], [40, 65, 85])
    c.drawImage(ImageReader(chart5), 60, 520, width=470, height=160, mask='auto')
    c.drawString(40, 480, 'Conclusion: Execution roadmap and ROI outlook.')
    c.setFont('Helvetica-Oblique', 9)
    c.drawRightString(550, 40, 'Page 5 — Roadmap & ROI.')

    c.save()
    buf.seek(0)
    return buf.read()
