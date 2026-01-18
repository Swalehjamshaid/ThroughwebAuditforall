
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import cm
import io
from typing import Dict, Any

PAGE_MARGIN = 2*cm

def draw_header_footer(c: canvas.Canvas, title: str, page: int):
    c.setFillColor(colors.HexColor('#0b5ed7'))
    c.rect(0, A4[1]-40, A4[0], 40, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold', 14)
    c.drawString(PAGE_MARGIN, A4[1]-28, f"FF Tech – AI Website Audit • {title}")
    c.setFillColor(colors.HexColor('#6c757d'))
    c.setFont('Helvetica', 9)
    c.drawRightString(A4[0]-PAGE_MARGIN, 20, f"Page {page} • Confidential • © FF Tech")


def _bar(c: canvas.Canvas, x, y, w, h, val, color=colors.HexColor('#0b5ed7')):
    c.setFillColor(colors.HexColor('#e9ecef'))
    c.rect(x, y, w, h, fill=1, stroke=0)
    c.setFillColor(color)
    c.rect(x, y, w*max(0,min(1,val/100.0)), h, fill=1, stroke=0)


def build_pdf(data: Dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    overall = data['overall']
    metrics = data['metrics']

    # Page 1 – Executive Summary
    draw_header_footer(c, 'Executive Summary', 1)
    c.setFont('Helvetica-Bold', 28)
    c.setFillColor(colors.HexColor('#212529'))
    c.drawString(PAGE_MARGIN, A4[1]-80, 'Executive Summary')

    y = A4[1]-120
    c.setFont('Helvetica', 12)
    c.drawString(PAGE_MARGIN, y, f"Overall Score: {overall['score']}  •  Grade: {overall['grade']}  •  Coverage: {overall['coverage']}%")
    _bar(c, PAGE_MARGIN, y-14, 14*cm, 10, overall['score'])

    # strengths / weaknesses / priorities
    c.setFont('Helvetica-Bold', 12)
    c.drawString(PAGE_MARGIN, y-50, 'Strengths')
    c.drawString(PAGE_MARGIN+7*cm, y-50, 'Weak Areas')
    c.drawString(PAGE_MARGIN+14*cm, y-50, 'Priority Fixes')

    c.setFont('Helvetica', 10)
    strengths = ['Good titles on most pages', 'Viewport present']
    weaknesses = ['Missing Open Graph tags', 'Multiple H1 on some pages']
    priorities = ['Fix 4xx/5xx errors', 'Add meta descriptions']
    for i, s in enumerate(strengths[:5]):
        c.drawString(PAGE_MARGIN, y-70-14*i, f"• {s}")
    for i, s in enumerate(weaknesses[:5]):
        c.drawString(PAGE_MARGIN+7*cm, y-70-14*i, f"• {s}")
    for i, s in enumerate(priorities[:5]):
        c.drawString(PAGE_MARGIN+14*cm, y-70-14*i, f"• {s}")

    c.showPage()

    # Page 2 – Site Health
    draw_header_footer(c, 'Site Health', 2)
    c.setFont('Helvetica-Bold', 20)
    c.drawString(PAGE_MARGIN, A4[1]-80, 'Overall Site Health')
    y = A4[1]-120
    items = [11,12,13,15,20]
    for mid in items:
        m = metrics.get(str(mid), {})
        label = m.get('name', f'Metric {mid}')
        score = m.get('score') or 0
        c.setFont('Helvetica', 11)
        c.drawString(PAGE_MARGIN, y, f"{label}")
        _bar(c, PAGE_MARGIN+8*cm, y-4, 9*cm, 8, score)
        y -= 22
    c.setFont('Helvetica', 10)
    c.setFillColor(colors.HexColor('#495057'))
    c.drawString(PAGE_MARGIN, y-10, 'Conclusion: Site health reflects error counts and page coverage. Reduce 4xx/5xx and ensure more pages are crawlable.')
    c.showPage()

    # Page 3 – Crawlability & On-Page
    draw_header_footer(c, 'Crawlability & On-Page', 3)
    c.setFont('Helvetica-Bold', 20)
    c.drawString(PAGE_MARGIN, A4[1]-80, 'Crawlability & On-Page SEO')
    y = A4[1]-120
    for mid in [21,22,23,24,41,49,50,62]:
        m = metrics.get(str(mid), {})
        label = m.get('name', f'Metric {mid}')
        score = m.get('score') or 0
        c.setFont('Helvetica', 11)
        c.drawString(PAGE_MARGIN, y, f"{label}")
        _bar(c, PAGE_MARGIN+8*cm, y-4, 9*cm, 8, score)
        y -= 22
    c.setFont('Helvetica', 10)
    c.setFillColor(colors.HexColor('#495057'))
    c.drawString(PAGE_MARGIN, y-10, 'Conclusion: Improve titles/H1 consistency and resolve client/server errors to boost crawlability.')
    c.showPage()

    # Page 4 – Performance, Mobile & Security
    draw_header_footer(c, 'Performance, Mobile & Security', 4)
    c.setFont('Helvetica-Bold', 20)
    c.drawString(PAGE_MARGIN, A4[1]-80, 'Performance • Mobile • Security')
    y = A4[1]-120
    for mid in [76,77,78,98,105,110]:
        m = metrics.get(str(mid), {"name":"Metric", "score":0})
        label = m.get('name', f'Metric {mid}')
        score = m.get('score') or 0
        c.setFont('Helvetica', 11)
        c.drawString(PAGE_MARGIN, y, f"{label}")
        _bar(c, PAGE_MARGIN+8*cm, y-4, 9*cm, 8, score)
        y -= 22
    c.setFont('Helvetica', 10)
    c.setFillColor(colors.HexColor('#495057'))
    c.drawString(PAGE_MARGIN, y-10, 'Conclusion: Add viewport for mobile, ensure HTTPS/SSL, and use PSI for Core Web Vitals to complete coverage.')
    c.showPage()

    # Page 5 – Opportunities & Competitors
    draw_header_footer(c, 'Opportunities & ROI', 5)
    c.setFont('Helvetica-Bold', 20)
    c.drawString(PAGE_MARGIN, A4[1]-80, 'Opportunities, Broken Links & Competitors')
    y = A4[1]-120
    for mid in [168,169,170,181,182,199,200]:
        m = metrics.get(str(mid), {"name":"Metric", "score":0})
        label = m.get('name', f'Metric {mid}')
        score = m.get('score') or 0
        c.setFont('Helvetica', 11)
        c.drawString(PAGE_MARGIN, y, f"{label}")
        _bar(c, PAGE_MARGIN+8*cm, y-4, 9*cm, 8, score)
        y -= 22
    c.setFont('Helvetica', 10)
    c.setFillColor(colors.HexColor('#495057'))
    c.drawString(PAGE_MARGIN, y-10, 'Conclusion: Prioritize fixing broken links and execute quick wins; expect measurable ROI improvements.')

    c.save()
    pdf = buf.getvalue()
    buf.close()
    return pdf
